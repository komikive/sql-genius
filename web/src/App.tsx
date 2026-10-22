import { Navigate, Route, Routes } from 'react-router-dom'

import { AppShell } from '@/components/layout/app-shell'
import { AdminDatasourcesPage } from '@/pages/AdminDatasourcesPage'
import { AdminHistoryPage } from '@/pages/AdminHistoryPage'
import { AdminMemoryPage } from '@/pages/AdminMemoryPage'
import { AdminQaPage } from '@/pages/AdminQaPage'
import { AdminSkillsPage } from '@/pages/AdminSkillsPage'
import { DatasourceDetailPage } from '@/pages/DatasourceDetailPage'
import { DatasourceWizardPage } from '@/pages/DatasourceWizardPage'
import { LandingPage } from '@/pages/LandingPage'
import { NotFoundPage } from '@/pages/NotFoundPage'
import { OverviewPage } from '@/pages/OverviewPage'
import { SkillPackDetailPage } from '@/pages/SkillPackDetailPage'
import { WorkbenchPage } from '@/pages/WorkbenchPage'

function App() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route element={<AppShell />}>
        <Route path="/overview" element={<OverviewPage />} />
        <Route path="/workbench" element={<WorkbenchPage />} />
        <Route path="/admin" element={<Navigate to="/admin/datasources" replace />} />
        <Route path="/admin/datasources" element={<AdminDatasourcesPage />} />
        <Route path="/admin/datasources/new" element={<DatasourceWizardPage />} />
        <Route path="/admin/datasources/:id" element={<DatasourceDetailPage />} />
        <Route path="/admin/skills" element={<AdminSkillsPage />} />
        <Route path="/admin/skills/:packId" element={<SkillPackDetailPage />} />
        <Route path="/admin/datasources/:id/skills/:packId" element={<SkillPackDetailPage />} />
        <Route path="/admin/memory" element={<AdminMemoryPage />} />
        <Route path="/admin/qa" element={<AdminQaPage />} />
        <Route path="/admin/history" element={<AdminHistoryPage />} />
      </Route>
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  )
}

export default App
