import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import { PublicOnly, RequireAuth } from "./components/RouteGuards";
import { Spinner } from "./components/ui";
import Login from "./pages/Login";
import Register from "./pages/Register";
import ForgotPassword from "./pages/ForgotPassword";
import ResetPassword from "./pages/ResetPassword";
import NotFound from "./pages/NotFound";

// Heavier pages load on demand so the first screen stays fast.
const Dashboard = lazy(() => import("./pages/Dashboard"));
const Projects = lazy(() => import("./pages/Projects"));
const ProjectLayout = lazy(() => import("./pages/project/ProjectLayout"));
const Overview = lazy(() => import("./pages/project/Overview"));
const ImportPage = lazy(() => import("./pages/project/ImportPage"));
const Review = lazy(() => import("./pages/project/Review"));
const Quality = lazy(() => import("./pages/project/Quality"));
const Exports = lazy(() => import("./pages/project/Exports"));
const Settings = lazy(() => import("./pages/project/Settings"));
const Activity = lazy(() => import("./pages/project/Activity"));
const Profile = lazy(() => import("./pages/Profile"));

export default function App() {
  return (
    <Suspense fallback={<Spinner className="min-h-screen" />}>
      <Routes>
        <Route element={<PublicOnly />}>
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route path="/forgot-password" element={<ForgotPassword />} />
        </Route>
        <Route path="/reset-password" element={<ResetPassword />} />
        <Route element={<RequireAuth />}>
          <Route element={<Layout />}>
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/projects" element={<Projects />} />
            <Route path="/projects/:projectId" element={<ProjectLayout />}>
              <Route index element={<Overview />} />
              <Route path="import" element={<ImportPage />} />
              <Route path="review" element={<Review />} />
              <Route path="quality" element={<Quality />} />
              <Route path="export" element={<Exports />} />
              <Route path="settings" element={<Settings />} />
              <Route path="activity" element={<Activity />} />
            </Route>
            <Route path="/profile" element={<Profile />} />
          </Route>
        </Route>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="*" element={<NotFound />} />
      </Routes>
    </Suspense>
  );
}
