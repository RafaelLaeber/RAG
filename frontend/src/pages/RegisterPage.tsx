import { useAuth } from '../auth/AuthContext'
import AuthForm from './AuthForm'

export default function RegisterPage() {
  const { register } = useAuth()
  return (
    <AuthForm
      mode="register"
      onSubmit={({ name, email, password }) => register(name, email, password)}
    />
  )
}
