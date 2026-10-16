import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Suspense, lazy } from "react";
import { AppProvider } from "./context/AppContext";
import Layout from "./components/Layout";
import PageSkeleton from "./components/PageSkeleton";
import ProtectedRoute from "./components/ProtectedRoute";
import ErrorBoundary from "./components/ErrorBoundary";

// ── Auth pages (eager — must load instantly for login flow) ──
import Home from "./pages/Home";
import Login from "./pages/Login";
import Register from "./pages/Register";
import OrcidCallback from "./pages/OrcidCallback";

// ── Lazy-loaded pages (route-level code splitting) ──
// Each group below uses Vite's magic comments for named chunks.
// Chunks are split by workflow phase to optimize mobile load:
//   phase-1-identity  → Identity
//   phase-2-design     → Topic, Questionnaire, Methodology
//   phase-3-fieldwork   → Fieldwork, Scenarios, Copilot
//   phase-4-analysis    → Analysis, Export
//   phase-5-knowledge   → Library, Literature, Memories
//   phase-community     → Community, Skills
//   phase-admin         → Admin
//   phase-settings      → Settings

// Phase 1: Identity & project setup
const Identity = lazy(() => import(
  /* webpackChunkName: "phase-1-identity" */ "./pages/Identity"
));

// Phase 2: Design
const TopicDesign = lazy(() => import(
  /* webpackChunkName: "phase-2-design" */ "./pages/TopicDesign"
));
const QuestionnaireDesign = lazy(() => import(
  /* webpackChunkName: "phase-2-design" */ "./pages/QuestionnaireDesign"
));
const MethodologyPlanning = lazy(() => import(
  /* webpackChunkName: "phase-2-design" */ "./pages/MethodologyPlanning"
));

// Phase 3: Fieldwork
const FieldworkTools = lazy(() => import(
  /* webpackChunkName: "phase-3-fieldwork" */ "./pages/FieldworkTools"
));
const Scenarios = lazy(() => import(
  /* webpackChunkName: "phase-3-fieldwork" */ "./pages/Scenarios"
));
const CopilotChat = lazy(() => import(
  /* webpackChunkName: "phase-3-fieldwork" */ "./pages/CopilotChat"
));

// Phase 4: Analysis
const Analysis = lazy(() => import(
  /* webpackChunkName: "phase-4-analysis" */ "./pages/Analysis"
));
const ReflectionPage = lazy(() => import(
  /* webpackChunkName: "phase-4-analysis" */ "./pages/ReflectionPage"
));
const Export = lazy(() => import(
  /* webpackChunkName: "phase-4-analysis" */ "./pages/Export"
));

// Phase 5: Knowledge library
const SurveyLibrary = lazy(() => import(
  /* webpackChunkName: "phase-5-knowledge" */ "./pages/SurveyLibrary"
));
const LiteratureSearch = lazy(() => import(
  /* webpackChunkName: "phase-5-knowledge" */ "./pages/LiteratureSearch"
));
const MyMemories = lazy(() => import(
  /* webpackChunkName: "phase-5-knowledge" */ "./pages/MyMemories"
));
const Collaboration = lazy(() => import(
  /* webpackChunkName: "phase-collaboration" */ "./pages/Collaboration"
));

// Community
const CommunityHome = lazy(() => import(
  /* webpackChunkName: "phase-community" */ "./pages/CommunityHome"
));
const SkillMarket = lazy(() => import(
  /* webpackChunkName: "phase-community" */ "./pages/SkillMarket"
));
const SkillDetailPage = lazy(() => import(
  /* webpackChunkName: "phase-community" */ "./pages/SkillDetail"
));
const PublishSkill = lazy(() => import(
  /* webpackChunkName: "phase-community" */ "./pages/PublishSkill"
));

// Settings & Admin
const Settings = lazy(() => import(
  /* webpackChunkName: "phase-settings" */ "./pages/Settings"
));
const Admin = lazy(() => import(
  /* webpackChunkName: "phase-admin" */ "./pages/Admin"
));

import "./App.css";

export default function App() {
  return (
    <AppProvider>
      <BrowserRouter>
        <Routes>
          {/* Auth pages — full-screen, no Layout shell, eager load */}
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route path="/orcid-callback" element={<OrcidCallback />} />

          {/* Admin — protected, inside Layout */}
          <Route
            element={
              <ProtectedRoute requireAdmin>
                <Layout />
              </ProtectedRoute>
            }
          >
            <Route
              path="admin"
              element={
                <Suspense fallback={<PageSkeleton />}>
                  <Admin />
                </Suspense>
              }
            />
          </Route>

          {/* Main app — authentication required, Layout shell */}
          <Route element={<ProtectedRoute><Layout /></ProtectedRoute>}>
            <Route index element={<Home />} />
            <Route path="identity" element={
              <Suspense fallback={<PageSkeleton />}><Identity /></Suspense>
            } />
            <Route path="topic" element={
              <Suspense fallback={<PageSkeleton />}><TopicDesign /></Suspense>
            } />
            <Route path="questionnaire" element={
              <Suspense fallback={<PageSkeleton />}><QuestionnaireDesign /></Suspense>
            } />
            <Route path="methodology" element={
              <Suspense fallback={<PageSkeleton />}><MethodologyPlanning /></Suspense>
            } />
            <Route path="fieldwork" element={
              <Suspense fallback={<PageSkeleton />}>
                <ErrorBoundary><FieldworkTools /></ErrorBoundary>
              </Suspense>
            } />
            <Route path="copilot" element={
              <Suspense fallback={<PageSkeleton />}><CopilotChat /></Suspense>
            } />
            <Route path="scenarios" element={
              <Suspense fallback={<PageSkeleton />}><Scenarios /></Suspense>
            } />
            <Route path="analysis" element={
              <Suspense fallback={<PageSkeleton />}><Analysis /></Suspense>
            } />
            <Route path="export" element={
              <Suspense fallback={<PageSkeleton />}><Export /></Suspense>
            } />
            <Route path="reflection" element={
              <Suspense fallback={<PageSkeleton />}><ReflectionPage /></Suspense>
            } />
            <Route path="library" element={
              <Suspense fallback={<PageSkeleton />}><SurveyLibrary /></Suspense>
            } />
            <Route path="literature" element={
              <Suspense fallback={<PageSkeleton />}><LiteratureSearch /></Suspense>
            } />
            <Route path="memories" element={
              <Suspense fallback={<PageSkeleton />}><MyMemories /></Suspense>
            } />
            <Route path="collaboration" element={
              <Suspense fallback={<PageSkeleton />}><Collaboration /></Suspense>
            } />
            <Route path="settings" element={
              <Suspense fallback={<PageSkeleton />}><Settings /></Suspense>
            } />
            <Route path="community" element={
              <Suspense fallback={<PageSkeleton />}><CommunityHome /></Suspense>
            } />
            <Route path="community/skills" element={
              <Suspense fallback={<PageSkeleton />}><SkillMarket /></Suspense>
            } />
            <Route path="community/skills/:id" element={
              <Suspense fallback={<PageSkeleton />}><SkillDetailPage /></Suspense>
            } />
            <Route path="community/publish" element={
              <Suspense fallback={<PageSkeleton />}><PublishSkill /></Suspense>
            } />
          </Route>
        </Routes>
      </BrowserRouter>
    </AppProvider>
  );
}
