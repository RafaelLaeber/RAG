import { useAuth } from '../auth/AuthContext'
import AuthForm from './AuthForm'

export default function LoginPage() {
  const { login } = useAuth()
  return <AuthForm mode="login" onSubmit={({ email, password }) => login(email, password)} />
}
