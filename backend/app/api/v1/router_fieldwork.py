"""Fieldwork endpoints — real-time ASR, file transcription, hints, session management."""

import json
import re
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, UploadFile, File, Form, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_ai_service, get_db, ensure_upload_dir
from app.api.deps_auth import require_user, get_current_profile
from app.models.user import UserAccount
from app.config import settings
from app.models.survey import SurveySession, UserProfile
from app.services.ai import AIService
from app.services.speech_engine import speech_engine
from app.services.emotion_tracker import emotion_tracker
from app.services.realtime_pipeline import realtime_pipeline
from app.services.interview_analyzer import interview_analyzer
from app.services.volcano_emotion import volcano_emotion
from app.services.fieldnote_service import generate_field_notes, list_notes, update_note, delete_note, export_notes
from app.services.asr import XunfeiASR
from app.services.asr_qwen import QwenRealtimeASR, qwen_filetrans
from app.services.url_safety import build_public_upload_url
from app.services.upload_validation import (
    SUPPORTED_UPLOAD_EXTENSIONS,
    UploadContentError,
    UploadEmptyError,
    UploadTooLargeError,
    save_upload_stream,
)
from app.skills.mode_prompts import get_interview_scenarios

import logging
logger = logging.getLogger(__name__)

router = APIRouter(tags=["fieldwork"])
_UPLOAD_FILE_ID_PATTERN = re.compile(r"^[0-9a-f]{12}$")


def _find_uploaded_file(file_id: str) -> Path | None:
    """Resolve only server-generated upload IDs within the upload directory."""

    if not _UPLOAD_FILE_ID_PATTERN.fullmatch(file_id):
        return None
    root = Path(ensure_upload_dir()).resolve()
    for candidate in root.glob(f"{file_id}.*"):
        resolved = candidate.resolve()
        if resolved.is_file() and resolved.parent == root:
            return resolved
    return None

# ── Theme-specific prompt modifiers ────────────────────────────────

THEME_MODIFIERS = {
    "academic": "请以学术严谨的风格输出。强调方法论规范性、理论对话和概念化表达。",
    "government": (
        "请以政务调研报告的风格输出。使用规范的公文用语，强调对策建议的可行性，"
        "突出基层治理、政策落实、民生保障等视角。"
    ),
    "youth": (
        "请以通俗易懂的风格输出，适合青年学生理解。在专业术语后附简要解释，"
        "引导学习者认识社会现象，注意融入马克思主义社会历史观的基本视角。"
    ),
}


def _theme_hint(theme: str) -> str:
    return THEME_MODIFIERS.get(theme, THEME_MODIFIERS["academic"])


# ── Status ──────────────────────────────────────────────────────────

@router.get("/fieldwork/status")
async def fieldwork_status():
    return {
        "asr_enabled": True,
        "recording": False,
        "session_duration_s": 0,
        "realtime_hints": [],
    }


@router.get("/fieldwork/scenarios")
async def fieldwork_scenarios(theme: str = "academic"):
    """Return preset interview scenario templates for the active mode."""
    scenarios = get_interview_scenarios(theme)
    return {"theme": theme, "scenarios": scenarios}


# ── Hints ───────────────────────────────────────────────────────────

@router.post("/fieldwork/hints")
async def fieldwork_hints(payload: dict, ai: AIService = Depends(get_ai_service)):
    """Generate real-time interviewing hints based on conversation context."""
    transcript_snippet = payload.get("transcript", "")
    scenario = payload.get("scenario", "community_interview")
    phase = payload.get("phase", "opening")
    theme = payload.get("theme", "academic")

    if not transcript_snippet.strip():
        return {"hints": []}

    prompt = (
        f"访谈场景: {scenario}\n访谈阶段: {phase}\n最近对话片段:\n{transcript_snippet}\n\n"
        "作为访谈教练，请提供3-5条即时建议：\n"
        "- 追问方向（如何深入当前话题）\n"
        "- 话术建议（具体可以说的话）\n"
        "- 注意事项（避免引导性问题、保持中立等）\n"
        "每条建议简短直接，用中文。输出为JSON数组格式: [\"建议1\", \"建议2\", ...]\n"
        f"{_theme_hint(theme)}"
    )
    messages = [
        {"role": "system", "content": "你是一位专业的田野调查访谈教练，实时为访谈者提供即时建议。保持建议简洁、可操作。输出纯JSON数组。"},
        {"role": "user", "content": prompt},
    ]
    result = await ai.chat(messages, temperature=0.5, max_tokens=1024, task="hints")
    return {"hints": result}


@router.post("/fieldwork/hints/stream")
async def fieldwork_hints_stream(payload: dict, ai: AIService = Depends(get_ai_service)):
    """Stream real-time interviewing hints via SSE."""
    transcript_snippet = payload.get("transcript", "")
    scenario = payload.get("scenario", "community_interview")
    phase = payload.get("phase", "opening")
    theme = payload.get("theme", "academic")

    if not transcript_snippet.strip():
        return {"hints": []}

    prompt = (
        f"访谈场景: {scenario}\n访谈阶段: {phase}\n最近对话片段:\n{transcript_snippet}\n\n"
        "作为访谈教练，请提供3-5条即时建议：\n"
        "- 追问方向（如何深入当前话题）\n"
        "- 话术建议（具体可以说的话）\n"
        "- 注意事项（避免引导性问题、保持中立等）\n"
        "每条建议简短直接，用中文。输出为JSON数组格式: [\"建议1\", \"建议2\", ...]\n"
        f"{_theme_hint(theme)}"
    )
    messages = [
        {"role": "system", "content": "你是一位专业的田野调查访谈教练，实时为访谈者提供即时建议。保持建议简洁、可操作。输出纯JSON数组。"},
        {"role": "user", "content": prompt},
    ]

    async def event_stream():
        async for token in ai.chat_stream(messages, temperature=0.5, max_tokens=1024, task="hints"):
            yield f"data: {json.dumps({'token': token})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ── Summarize ───────────────────────────────────────────────────────

@router.post("/fieldwork/summarize")
async def fieldwork_summarize(payload: dict, ai: AIService = Depends(get_ai_service)):
    """Summarize a fieldwork transcript into structured notes."""
    transcript = payload.get("transcript", "")
    theme = payload.get("theme", "academic")
    if not transcript.strip():
        return {"error": "transcript is required"}

    prompt = (
        "请对以下田野/访谈记录进行结构化摘要：\n\n"
        f"{transcript}\n\n"
        "输出格式（Markdown）：\n"
        "1. **核心发现**（3-5个关键点）\n"
        "2. **主题编码**（识别2-4个主要主题）\n"
        "3. **情感基调**（整体语气和情绪倾向）\n"
        "4. **待追问的问题**（未充分展开的话题）\n"
        "5. **方法论反思**（访谈技巧层面的改进建议）\n"
        f"{_theme_hint(theme)}"
    )
    messages = [
        {"role": "system", "content": "你是一位田野调查分析助手，擅长从访谈文本中提取结构化信息。"},
        {"role": "user", "content": prompt},
    ]
    result = await ai.chat(messages, temperature=0.5, max_tokens=3072, task="analysis")
    return {"summary": result}


@router.post("/fieldwork/summarize/stream")
async def fieldwork_summarize_stream(payload: dict, ai: AIService = Depends(get_ai_service)):
    """Stream structured fieldwork summary via SSE."""
    transcript = payload.get("transcript", "")
    theme = payload.get("theme", "academic")
    if not transcript.strip():
        return {"error": "transcript is required"}

    prompt = (
        "请对以下田野/访谈记录进行结构化摘要：\n\n"
        f"{transcript}\n\n"
        "输出格式（Markdown）：\n"
        "1. **核心发现**（3-5个关键点）\n"
        "2. **主题编码**（识别2-4个主要主题）\n"
        "3. **情感基调**（整体语气和情绪倾向）\n"
        "4. **待追问的问题**（未充分展开的话题）\n"
        "5. **方法论反思**（访谈技巧层面的改进建议）\n"
        f"{_theme_hint(theme)}"
    )
    messages = [
        {"role": "system", "content": "你是一位田野调查分析助手，擅长从访谈文本中提取结构化信息。"},
        {"role": "user", "content": prompt},
    ]

    async def event_stream():
        async for token in ai.chat_stream(messages, temperature=0.5, max_tokens=3072, task="analysis"):
            yield f"data: {json.dumps({'token': token})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ── Session CRUD ────────────────────────────────────────────────────

@router.post("/fieldwork/sessions")
async def create_session(payload: dict, db: AsyncSession = Depends(get_db),
                         ai: AIService = Depends(get_ai_service)):
    session = SurveySession(
        project_id=payload.get("project_id", 0),
        transcript_text=payload.get("transcript_text", ""),
        notes=payload.get("notes", ""),
        summary_text=payload.get("summary_text", ""),
        hints_generated=payload.get("hints_generated", ""),
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)

    # ── Auto-generate field notes if transcript provided ──
    field_notes_preview = []
    transcript = payload.get("transcript_text", "")
    if transcript and len(transcript.strip()) >= 50:
        scenario = payload.get("scenario", "community_interview")
        theme = payload.get("theme", "academic")
        try:
            notes = await generate_field_notes(
                db, ai, session.id, transcript, scenario=scenario, theme=theme,
            )
            field_notes_preview = [
                {"id": n.id, "note_type": n.note_type, "content": n.content[:120]}
                for n in notes[:4]
            ]
        except Exception as e:
            logger.warning("Auto field note generation failed for session %s: %s", session.id, e)

    return {
        "id": session.id,
        "project_id": session.project_id,
        "created_at": str(session.created_at) if session.created_at else None,
        "field_notes_count": len(field_notes_preview),
        "field_notes_preview": field_notes_preview,
    }


@router.patch("/fieldwork/sessions/{session_id}")
async def update_session(session_id: int, payload: dict, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(SurveySession).where(SurveySession.id == session_id))
    session = result.scalar_one_or_none()
    if not session:
        return {"error": "Session not found"}

    for field in ["transcript_text", "notes", "summary_text", "hints_generated"]:
        if field in payload:
            setattr(session, field, payload[field])

    await db.commit()
    await db.refresh(session)
    return {
        "id": session.id,
        "updated_at": str(session.updated_at) if session.updated_at else None,
    }


# ── Field Notes ──────────────────────────────────────────────────────

@router.get("/fieldwork/sessions/{session_id}/notes")
async def get_session_notes(
    session_id: int,
    note_type: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """List field notes for a session, optionally filtered by type."""
    notes = await list_notes(db, session_id, note_type=note_type)
    return {
        "notes": [
            {
                "id": n.id,
                "note_type": n.note_type,
                "content": n.content,
                "timestamp_in_recording": n.timestamp_in_recording,
                "tags": n.tags,
                "ai_generated": n.ai_generated,
                "ai_edited": n.ai_edited,
                "sort_order": n.sort_order,
                "created_at": str(n.created_at) if n.created_at else None,
            }
            for n in notes
        ],
        "total": len(notes),
    }


@router.patch("/fieldwork/notes/{note_id}")
async def edit_note(
    note_id: int,
    payload: dict,
    profile: UserProfile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    """Edit a field note's content."""
    content = payload.get("content", "")
    note = await update_note(db, note_id, content, editor_profile_id=profile.id)
    if note is None:
        return {"error": "Note not found"}
    return {
        "id": note.id,
        "content": note.content,
        "ai_edited": note.ai_edited,
        "updated_at": str(note.updated_at) if note.updated_at else None,
    }


@router.delete("/fieldwork/notes/{note_id}")
async def remove_note(note_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a field note."""
    ok = await delete_note(db, note_id)
    if not ok:
        return {"error": "Note not found"}
    return {"deleted": True, "id": note_id}


@router.post("/fieldwork/sessions/{session_id}/notes/generate")
async def regenerate_notes(
    session_id: int,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    ai: AIService = Depends(get_ai_service),
):
    """Manually trigger field note regeneration for a session."""
    result = await db.execute(select(SurveySession).where(SurveySession.id == session_id))
    session = result.scalar_one_or_none()
    if not session:
        return {"error": "Session not found"}
    transcript = payload.get("transcript_text") or session.transcript_text or ""
    if not transcript.strip():
        return {"error": "No transcript available for note generation"}
    scenario = payload.get("scenario", "community_interview")
    theme = payload.get("theme", "academic")
    notes = await generate_field_notes(db, ai, session_id, transcript, scenario=scenario, theme=theme)
    return {
        "generated": len(notes),
        "notes": [
            {"id": n.id, "note_type": n.note_type, "content": n.content[:120]}
            for n in notes
        ],
    }


@router.get("/fieldwork/sessions/{session_id}/notes/export")
async def export_session_notes(
    session_id: int,
    fmt: str = "markdown",
    db: AsyncSession = Depends(get_db),
):
    """Export field notes for a session (markdown or json)."""
    from fastapi.responses import PlainTextResponse
    result = await export_notes(db, session_id, fmt=fmt)
    media = "application/json" if fmt == "json" else "text/markdown; charset=utf-8"
    return PlainTextResponse(content=result, media_type=media)


# ── WebSocket ASR — Xunfei (legacy) ─────────────────────────────────

@router.websocket("/fieldwork/asr")
async def fieldwork_asr_ws(ws: WebSocket):
    await ws.accept()
    asr = XunfeiASR()
    transcript_buffer: list[str] = []

    async def on_end(transcript: str):
        if transcript.strip():
            transcript_buffer.append(transcript)
            try:
                await ws.send_text(json.dumps({
                    "type": "segment_complete",
                    "text": transcript,
                    "timestamp": time.time(),
                }))
            except Exception:
                logger.warning("Failed to send segment_complete to client", exc_info=True)

    try:
        await asr.relay(ws, on_end_callback=on_end)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await ws.send_text(json.dumps({"type": "error", "message": str(e)}))
        except Exception:
            logger.warning("Failed to send error to client", exc_info=True)
    finally:
        full_text = "".join(transcript_buffer)
        if full_text:
            logger.info("Xunfei ASR session ended: %d segments, %d chars",
                        len(transcript_buffer), len(full_text))


# ── WebSocket ASR — Qwen Paraformer ─────────────────────────────────

@router.websocket("/fieldwork/asr/qwen")
async def fieldwork_asr_qwen_ws(ws: WebSocket):
    await ws.accept()
    asr = QwenRealtimeASR()
    transcript_buffer: list[str] = []

    async def on_end(transcript: str):
        if transcript.strip():
            transcript_buffer.append(transcript)
            try:
                await ws.send_text(json.dumps({
                    "type": "segment_complete",
                    "text": transcript,
                    "timestamp": time.time(),
                }))
            except Exception:
                logger.warning("Failed to send segment_complete to client", exc_info=True)

    try:
        await asr.relay(ws, on_end_callback=on_end)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await ws.send_text(json.dumps({"type": "error", "message": str(e)}))
        except Exception:
            logger.warning("Failed to send error to client", exc_info=True)
    finally:
        full_text = "".join(transcript_buffer)
        if full_text:
            logger.info("Qwen ASR session ended: %d segments, %d chars",
                        len(transcript_buffer), len(full_text))


# ── File Upload Transcription ───────────────────────────────────────

@router.post("/fieldwork/transcribe-file")
async def transcribe_uploaded_file(
    file: UploadFile = File(...),
    language: str = Form("zh"),
    db: AsyncSession = Depends(get_db),
):
    """Upload an audio/video file for transcription via Qwen3-ASR-Filetrans.

    Accepts the configured media formats up to ``MAX_UPLOAD_MB``.
    Auto-submits to Qwen FileTrans if API key is configured and file URL is accessible.
    """
    upload_dir = Path(ensure_upload_dir())
    suffix = Path(file.filename or "audio.wav").suffix.lower()
    if suffix not in SUPPORTED_UPLOAD_EXTENSIONS:
        return {
            "error": (
                f"Unsupported format '{suffix}'. Supported: "
                f"{', '.join(sorted(SUPPORTED_UPLOAD_EXTENSIONS))}"
            )
        }

    file_id = uuid.uuid4().hex[:12]
    safe_name = f"{file_id}{suffix}"
    filepath = upload_dir / safe_name
    max_upload_bytes = settings.max_upload_mb * 1024 * 1024
    try:
        file_size_bytes = await save_upload_stream(
            file, filepath, suffix, max_upload_bytes
        )
    except UploadTooLargeError as exc:
        size_mb = exc.size_bytes / (1024 * 1024)
        return {
            "error": (
                f"File too large ({size_mb:.1f}MB). "
                f"Maximum: {settings.max_upload_mb}MB"
            )
        }
    except UploadEmptyError:
        return {"error": "Uploaded file is empty"}
    except UploadContentError:
        return {"error": "Uploaded content does not match its file extension"}

    file_size_mb = file_size_bytes / (1024 * 1024)

    api_ready = bool(qwen_filetrans.api_key)
    public_url_ready = False
    file_url = ""
    if api_ready:
        try:
            file_url = build_public_upload_url(settings.public_base_url, safe_name)
            public_url_ready = True
        except ValueError:
            logger.warning("Skipping FileTrans: PUBLIC_BASE_URL is not a safe HTTPS URL")

    result = {
        "status": "saved",
        "file_id": file_id,
        "filename": file.filename,
        "size_mb": round(file_size_mb, 2),
        "format": suffix.lstrip("."),
        "api_key_ready": api_ready,
    }

    # Auto-submit to Qwen FileTrans if API key is configured
    if api_ready and public_url_ready:
        logger.info("FileTrans attempt for uploaded file %s", file_id)
        try:
            task_id = await qwen_filetrans.submit(file_url, language)
            result["status"] = "transcribing"
            result["task_id"] = task_id
            result["message"] = f"Submitted for transcription. Task: {task_id}"
            try:
                trans_result = await qwen_filetrans.poll(task_id, max_wait_s=600, interval_s=3)
                result["status"] = "completed"
                result["transcript"] = trans_result.get("transcription", "")
                result["sentences"] = trans_result.get("sentences", [])
                result["message"] = "Transcription completed."
            except TimeoutError:
                result["status"] = "processing"
                result["message"] = f"Still processing. Poll task {task_id} later."
            except Exception as e:
                result["status"] = "transcribe_failed"
                result["message"] = "Saved, but transcription failed."
        except Exception as e:
            logger.warning("FileTrans submit failed; falling back to WebSocket transcription", exc_info=True)
            # ── Fallback: WebSocket-based Paraformer transcription ──
            try:
                ws_asr = QwenRealtimeASR()
                transcript = await ws_asr.transcribe_file(str(filepath))
                if transcript.strip():
                    result["status"] = "completed"
                    result["transcript"] = transcript
                    result["message"] = "Transcription completed (WebSocket fallback)."
                else:
                    result["status"] = "submit_failed"
                    result["message"] = f"Both FileTrans and WebSocket failed: empty transcript"
            except Exception as ws_e:
                result["status"] = "submit_failed"
                result["message"] = "Saved, but transcription submission failed."
    elif not api_ready:
        result["message"] = "File saved. QWEN_API_KEY not configured — set it to enable transcription."
    else:
        result["message"] = "File saved. Configure a public HTTPS PUBLIC_BASE_URL to enable provider transcription."

    return result


@router.post("/fieldwork/transcribe-file/{file_id}/process")
async def process_transcription(file_id: str, payload: dict):
    """Submit a previously uploaded file for Qwen Filetrans processing.

    The provider URL is always derived from a server-owned upload ID and
    deployment-owned PUBLIC_BASE_URL. Client-provided file URLs are ignored.
    """
    uploaded_file = _find_uploaded_file(file_id)
    if uploaded_file is None:
        return {"error": "Uploaded file not found"}

    try:
        file_url = build_public_upload_url(settings.public_base_url, uploaded_file.name)
    except ValueError:
        return {"error": "A safe HTTPS PUBLIC_BASE_URL is required before provider submission"}

    language = payload.get("language", "zh")

    try:
        task_id = await qwen_filetrans.submit(file_url, language)
        result = await qwen_filetrans.poll(task_id)
        return {
            "status": "completed",
            "file_id": file_id,
            "transcript": result.get("transcription", ""),
            "sentences": result.get("sentences", []),
        }
    except Exception as e:
        return {"error": "Transcription failed", "file_id": file_id}


@router.post("/fieldwork/transcribe-file/{file_id}/analyze")
async def analyze_transcript(file_id: str, payload: dict, ai: AIService = Depends(get_ai_service)):
    """Run AI analysis on a transcribed text.

    Body: {"transcript": "...", "theme": "academic"}
    """
    transcript = payload.get("transcript", "")
    theme = payload.get("theme", "academic")

    if not transcript.strip():
        return {"error": "transcript required"}

    prompt = (
        "请对以下田野访谈转写文本进行深度分析：\n\n"
        f"{transcript[:6000]}\n\n"
        "1. **核心主题识别**（3-5个主要主题，附支持性引用）\n"
        "2. **情感与态度分析**（受访者情绪倾向和态度变化）\n"
        "3. **关键引述**（5-8条具有分析价值的关键发言）\n"
        "4. **矛盾与张力**（访谈中出现的观点矛盾）\n"
        "5. **理论关联**（与相关社会学理论的对话点）\n"
        "6. **方法建议**（后续访谈或分析的改进方向）\n"
        f"{_theme_hint(theme)}"
    )

    messages = [
        {"role": "system", "content": "你是一位专业的田野调查和质性数据分析专家。"},
        {"role": "user", "content": prompt},
    ]

    result = await ai.chat(messages, temperature=0.5, max_tokens=4096, task="analysis")
    return {"analysis": result, "file_id": file_id}


# ============================================================
# v0.3 Enhanced Endpoints — Emotion, Analysis, Pipeline
# ============================================================

@router.get('/fieldwork/speech-status')
async def speech_engine_status():
    from app.services.speech_engine import funasr_engine
    return {
        'funasr_available': funasr_engine.available,
        'funasr_device': settings.funasr_device,
        'qwen_api_ready': bool(settings.qwen_api_key),
        'emotion_enabled': settings.emotion_enabled,
    }

@router.post('/fieldwork/transcribe-enhanced')
async def transcribe_enhanced(file: UploadFile = File(...), language: str = Form('zh'), with_emotion: bool = Form(True)):
    upload_dir = Path(ensure_upload_dir())
    suffix = Path(file.filename or 'audio.wav').suffix.lower()
    if suffix not in SUPPORTED_UPLOAD_EXTENSIONS:
        return {'error': f'Unsupported format: {suffix}'}
    file_id = uuid.uuid4().hex[:12]
    safe_name = f'{file_id}{suffix}'
    filepath = upload_dir / safe_name
    max_upload_bytes = settings.max_upload_mb * 1024 * 1024
    try:
        file_size_bytes = await save_upload_stream(
            file, filepath, suffix, max_upload_bytes
        )
    except UploadTooLargeError as exc:
        size_mb = exc.size_bytes / (1024 * 1024)
        return {
            'error': f'Too large ({size_mb:.1f}MB). Max {settings.max_upload_mb}MB'
        }
    except UploadEmptyError:
        return {'error': 'Uploaded file is empty'}
    except UploadContentError:
        return {'error': 'Uploaded content does not match its file extension'}
    try:
        result = await speech_engine.process_file(str(filepath), language=language, with_emotion=with_emotion, with_speaker=True)
        return {
            'status': 'completed', 'file_id': file_id, 'filename': file.filename,
            'duration_s': result.duration_ms / 1000, 'engine_used': result.engine_used,
            'speaker_count': result.speaker_count, 'emotion_summary': result.emotion_summary,
            'transcript': result.text,
            'segments': [{'start_ms':s.start_ms,'end_ms':s.end_ms,'speaker_id':s.speaker_id,'speaker_label':s.speaker_label,'text':s.text,'emotion':s.emotion,'emotion_confidence':s.emotion_confidence} for s in result.segments],
        }
    except Exception as e:
        logger.exception(f'Enhanced transcription failed: {e}')
        return {'status':'failed','file_id':file_id,'error':'Transcription failed'}

@router.post('/fieldwork/analyze-deep')
async def analyze_interview_deep(payload: dict):
    transcript = payload.get('transcript','')
    if not transcript.strip():
        return {'error':'transcript is required'}
    a = await interview_analyzer.analyze(transcript=transcript, segments=payload.get('segments',[]), emotion_timeline=payload.get('emotion_timeline'), theme=payload.get('theme','academic'))
    return {
        'overall_mood':a.overall_mood,'mood_stability':a.mood_stability,'emotional_peaks':a.emotional_peaks,
        'core_themes':a.core_themes,'key_quotes':a.key_quotes,'contradictions':a.contradictions,
        'unaddressed_topics':a.unaddressed_topics,'quality_scores':a.quality_scores,
        'theory_connections':a.theory_connections,'method_suggestions':a.method_suggestions,
        'next_steps':a.next_steps,'full_analysis_text':a.full_analysis_text,
    }

@router.post('/fieldwork/cross-analyze')
async def cross_analyze_interviews(payload: dict):
    interviews = payload.get('interviews',[])
    if not interviews: return {'error':'interviews list required'}
    if len(interviews) > 10: return {'error':'Max 10 interviews per batch'}
    r = await interview_analyzer.cross_analyze(interviews, theme=payload.get('theme','academic'))
    return {'interview_count':r.interview_count,'shared_themes':r.shared_themes,'divergent_themes':r.divergent_themes,'emotion_comparison':r.emotion_comparison,'saturation_assessment':r.saturation_assessment,'overall_insights':r.overall_insights}

@router.websocket('/fieldwork/pipeline')
async def fieldwork_pipeline_ws(ws: WebSocket):
    """Real-time interview pipeline: mixed binary PCM (audio) + JSON text (facial signals).

    Client sends:
      - Binary: PCM 16kHz 16bit mono audio frames
      - Text JSON: {"type": "facial_signal", "signal": {FacialSignal...}}
      - Text JSON: {"type": "end"} to finish ASR
      - Text JSON: {"type": "ping"} for keepalive

    Server returns JSON: transcript segments, emotion_alerts, coach_hints, summaries.
    """
    params = {}
    if '?' in str(ws.url):
        qs = str(ws.url).split('?')[-1]
        params = dict(p.split('=') for p in qs.split('&') if '=' in p)
    await realtime_pipeline.handle(ws, session_id=params.get('session_id',''), scenario=params.get('scenario','community_interview'), theme=params.get('theme','academic'), phase=params.get('phase','opening'))


@router.websocket('/fieldwork/facial')
async def fieldwork_facial_ws(ws: WebSocket):
    """Lightweight WebSocket for facial emotion signals (CameraCapture → EmotionTracker).

    Client sends: {"type": "facial_signal", "signal": {FacialSignal...}}
    Server returns: {"type": "emotion_alert", ...} when an alert triggers.

    Uses the shared emotion_tracker singleton — coexists with /pipeline for bimodal fusion.
    """
    await ws.accept()
    session_id = f"facial_{int(time.time())}"
    emotion_tracker.start_session(session_id)
    logger.info(f"Facial WS session started: {session_id}")

    try:
        while True:
            data = await ws.receive_text()
            msg = json.loads(data)
            if msg.get("type") == "facial_signal":
                signal = msg.get("signal", {})
                if signal:
                    sample = emotion_tracker.feed_facial(signal)
                    if sample:
                        alert = emotion_tracker.current_alert()
                        if alert:
                            await ws.send_json({
                                "type": "emotion_alert",
                                "emotion": emotion_tracker.get_recent_emotion(window_s=30),
                                "message": alert.message,
                                "suggested_action": alert.suggested_action,
                                "urgency": alert.urgency,
                                "timestamp_ms": int((time.time() - emotion_tracker._started_at) * 1000),
                            })
            elif msg.get("type") == "ping":
                await ws.send_json({"type": "pong"})
    except WebSocketDisconnect:
        logger.info(f"Facial WS disconnected: {session_id}")
    except Exception as e:
        logger.warning(f"Facial WS error: {e}")
    finally:
        timeline = emotion_tracker.end_session()
        try:
            await ws.send_json({
                "type": "session_ended",
                "session_id": session_id,
                "overall_mood": timeline.overall_mood,
                "mood_stability": timeline.mood_stability,
                "emotional_peaks": timeline.emotional_peaks,
            })
        except Exception:
            pass

@router.get('/fieldwork/emotion-timeline/{session_id}')
async def get_emotion_timeline(session_id: str):
    t = emotion_tracker.get_timeline()
    return {'session_id':session_id,'overall_mood':t.overall_mood,'mood_stability':t.mood_stability,'emotional_peaks':t.emotional_peaks,'samples':[{'timestamp_ms':s.timestamp_ms,'fused_emotion':s.fused_emotion,'fused_intensity':s.fused_intensity} for s in t.samples]}

@router.get('/fieldwork/volcano-status')
async def volcano_status():
    """Check Volcano Engine ARK API connectivity."""
    if not settings.volcano_api_key:
        return {'available': False, 'reason': 'API key not configured'}
    healthy = await volcano_emotion.health()
    return {
        'available': healthy,
        'model': settings.volcano_emotion_model,
        'base_url': settings.volcano_base_url,
        'emotion_enabled': settings.volcano_emotion_enabled,
    }
