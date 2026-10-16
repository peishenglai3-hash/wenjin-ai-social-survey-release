"""Field note mutation ownership regression tests."""

import pytest
from sqlalchemy import select

from app.models.survey import FieldNote, SurveyProject, SurveySession, UserProfile
from app.models.user import UserAccount


async def _foreign_note(db_session):
    foreign_profile = UserProfile(user_id=None, role="researcher")
    db_session.add(foreign_profile)
    await db_session.flush()
    project = SurveyProject(profile_id=foreign_profile.id, title="foreign notes project")
    db_session.add(project)
    await db_session.flush()
    session = SurveySession(project_id=project.id, transcript_text="private transcript")
    db_session.add(session)
    await db_session.flush()
    note = FieldNote(session_id=session.id, content="private note")
    db_session.add(note)
    await db_session.commit()
    await db_session.refresh(note)
    return note


class TestFieldNoteOwnership:
    @pytest.mark.asyncio
    async def test_foreign_note_cannot_be_edited_or_deleted(self, client, db_session):
        note = await _foreign_note(db_session)

        edit = await client.patch(
            f"/api/v1/fieldwork/notes/{note.id}",
            json={"content": "tampered"},
        )
        delete = await client.delete(f"/api/v1/fieldwork/notes/{note.id}")

        assert edit.json() == {"error": "Note not found"}
        assert delete.json() == {"error": "Note not found"}
        persisted = await db_session.scalar(
            select(FieldNote).where(FieldNote.id == note.id)
        )
        assert persisted is not None
        assert persisted.content == "private note"

    @pytest.mark.asyncio
    async def test_current_profile_can_edit_and_delete_note(self, client, db_session):
        current_profile = await db_session.scalar(
            select(UserProfile)
            .join(UserAccount, UserAccount.id == UserProfile.user_id)
            .where(UserAccount.email == "test-researcher@example.invalid")
        )
        project = SurveyProject(profile_id=current_profile.id, title="owned notes project")
        db_session.add(project)
        await db_session.flush()
        session = SurveySession(project_id=project.id, transcript_text="owned transcript")
        db_session.add(session)
        await db_session.flush()
        note = FieldNote(session_id=session.id, content="owned note")
        db_session.add(note)
        await db_session.commit()
        await db_session.refresh(note)

        edit = await client.patch(
            f"/api/v1/fieldwork/notes/{note.id}",
            json={"content": "edited note"},
        )
        delete = await client.delete(f"/api/v1/fieldwork/notes/{note.id}")

        assert edit.json()["content"] == "edited note"
        assert delete.json() == {"deleted": True, "id": note.id}
