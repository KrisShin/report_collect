import { Navigate, createBrowserRouter } from 'react-router-dom'
import SubmitPage from './client/SubmitPage'
import SuccessPage from './client/SuccessPage'
import AdminLayout from './admin/AdminLayout'
import LoginPage from './admin/LoginPage'
import SubmissionsPage from './admin/SubmissionsPage'

export const router = createBrowserRouter([
  { path: '/', element: <Navigate to="/m" replace /> },
  { path: '/m', element: <SubmitPage /> },
  { path: '/m/success', element: <SuccessPage /> },
  { path: '/admin/login', element: <LoginPage /> },
  {
    path: '/admin',
    element: <AdminLayout />,
    children: [{ index: true, element: <SubmissionsPage /> }],
  },
  { path: '*', element: <Navigate to="/m" replace /> },
])
