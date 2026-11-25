import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider, useAuth } from './auth/AuthContext'
import ChatPage from './pages/ChatPage'
import LoginPage from './pages/LoginPage'
import RegisterPage from './pages/RegisterPage'

function Splash() {
  return (
    <div className="splash" role="status">
      Carregando…
    </div>
  )
}

function RequireAuth({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth()
  if (loading) return <Splash />
  if (!user) return <Navigate to="/login" replace />
  return children
}

/** Quem já tem sessão não precisa ver login/registro. */
function GuestOnly({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth()
  if (loading) return <Splash />
  if (user) return <Navigate to="/" replace />
  return children
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route
            path="/login"
            element={
              <GuestOnly>
                <LoginPage />
              </GuestOnly>
            }
          />
          <Route
            path="/registro"
            element={
              <GuestOnly>
                <RegisterPage />
              </GuestOnly>
            }
          />
          <Route
            path="/"
            element={
              <RequireAuth>
                <ChatPage />
              </RequireAuth>
            }
          />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  )
}
