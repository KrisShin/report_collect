import { lazy } from 'react'
import { Navigate, createBrowserRouter } from 'react-router-dom'
import LazyPage from './shared/LazyPage'

const ClientHome = lazy(() => import('./client/ClientHome'))
const SubmitPage = lazy(() => import('./client/SubmitPage'))
const SuccessPage = lazy(() => import('./client/SuccessPage'))
const LoginPage = lazy(() => import('./admin/LoginPage'))
const AdminRoot = lazy(() => import('./admin/AdminRoot'))
const AdminLayout = lazy(() => import('./admin/AdminLayout'))
const SubmissionsPage = lazy(() => import('./admin/SubmissionsPage'))
const ReportsPage = lazy(() => import('./admin/ReportsPage'))

const wrap = (node: React.ReactNode) => <LazyPage>{node}</LazyPage>

export const router = createBrowserRouter([
  { path: '/', element: <Navigate to="/m" replace /> },
  { path: '/m', element: wrap(<ClientHome />) },
  { path: '/m/success', element: wrap(<SuccessPage />) },
  { path: '/m/:reportId', element: wrap(<SubmitPage />) },
  { path: '/admin/login', element: wrap(<LoginPage />) },
  {
    path: '/admin',
    element: wrap(<AdminRoot />),
    children: [
      {
        element: wrap(<AdminLayout />),
        children: [
          { index: true, element: wrap(<SubmissionsPage />) },
          { path: 'reports', element: wrap(<ReportsPage />) },
        ],
      },
    ],
  },
  { path: '*', element: <Navigate to="/m" replace /> },
])
