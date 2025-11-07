import { useState, useEffect } from 'react'
import './App.css'

// Use empty string for production (same domain), fallback to localhost for local dev
const API_URL = import.meta.env.VITE_API_URL !== undefined 
  ? import.meta.env.VITE_API_URL 
  : 'http://localhost:8000'

interface Todo {
  id: number
  title: string
  description?: string
  completed: boolean
  created_at: string
}

function App() {
  const [todos, setTodos] = useState<Todo[]>([])
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')

  useEffect(() => {
    fetch(`${API_URL}/api/todos`).then(r => r.json()).then(setTodos)
  }, [])

  const addTodo = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!title.trim()) return

    const res = await fetch(`${API_URL}/api/todos`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, description: description || null }),
    })
    const newTodo = await res.json()
    setTodos([...todos, newTodo])
    setTitle('')
    setDescription('')
  }

  const toggleTodo = async (todo: Todo) => {
    const res = await fetch(`${API_URL}/api/todos/${todo.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ completed: !todo.completed }),
    })
    const updated = await res.json()
    setTodos(todos.map(t => t.id === todo.id ? updated : t))
  }

  const deleteTodo = async (id: number) => {
    await fetch(`${API_URL}/api/todos/${id}`, { method: 'DELETE' })
    setTodos(todos.filter(t => t.id !== id))
  }

  return (
    <div className="app">
      <div className="container">
        <header>
          <h1>📝 Todo App</h1>
        </header>

        <form onSubmit={addTodo} className="todo-form">
          <input
            type="text"
            placeholder="What needs to be done?"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className="input-title"
          />
          <input
            type="text"
            placeholder="Description (optional)"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            className="input-description"
          />
          <button type="submit" disabled={!title.trim()}>
            Add Todo
          </button>
        </form>

        {todos.length === 0 ? (
          <div className="empty">No todos yet!</div>
        ) : (
          <div className="todo-list">
            {todos.map((todo) => (
              <div key={todo.id} className={`todo-item ${todo.completed ? 'completed' : ''}`}>
                <input
                  type="checkbox"
                  checked={todo.completed}
                  onChange={() => toggleTodo(todo)}
                />
                <div className="todo-text">
                  <h3>{todo.title}</h3>
                  {todo.description && <p>{todo.description}</p>}
                </div>
                <button onClick={() => deleteTodo(todo.id)}>Delete</button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

export default App

