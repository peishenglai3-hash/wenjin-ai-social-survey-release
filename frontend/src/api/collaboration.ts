import api from "./client";

export interface CollaborationMember {
  id: number;
  project_id: number;
  profile_id: number;
  role: "owner" | "editor" | "reviewer" | "viewer";
  status: string;
  created_at: string | null;
  updated_at: string | null;
}

export interface ResearchArtifact {
  id: number;
  project_id: number;
  artifact_key: string;
  kind: string;
  title: string;
  created_by_profile_id: number | null;
  status: string;
  created_at: string | null;
  updated_at: string | null;
}

export interface PaginationMeta {
  limit: number;
  offset: number;
  has_more: boolean;
  next_offset: number | null;
}

export async function listCollaborationMembers(projectId: number) {
  const response = await api.get<{ members: CollaborationMember[]; pagination: PaginationMeta }>(
    `/collaboration/projects/${projectId}/members`,
    { params: { limit: 50, offset: 0 } },
  );
  return response.data;
}

export async function listResearchArtifacts(projectId: number) {
  const response = await api.get<{ artifacts: ResearchArtifact[]; pagination: PaginationMeta }>(
    `/collaboration/projects/${projectId}/artifacts`,
    { params: { limit: 50, offset: 0 } },
  );
  return response.data;
}

export async function createResearchArtifact(
  projectId: number,
  payload: { artifact_key: string; kind: string; title: string },
) {
  const response = await api.post<{ created: boolean; artifact: ResearchArtifact }>(
    `/collaboration/projects/${projectId}/artifacts`,
    payload,
  );
  return response.data;
}
