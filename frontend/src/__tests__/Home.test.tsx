import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { AppProvider } from '../context/AppContext'
import Home from '../pages/Home'

// The provider probes the HttpOnly refresh-cookie session on mount. Keep this
// page unit test hermetic instead of waiting for a real backend.
vi.mock('../api/client', () => ({
  default: {
    post: vi.fn(() => Promise.reject(new Error('no test session'))),
    get: vi.fn(() => Promise.reject(new Error('no test session'))),
  },
  setAccessToken: vi.fn(),
  getAccessToken: vi.fn(() => null),
}))

const mockFetch = vi.fn()
globalThis.fetch = mockFetch

const localStorageMock = (() => {
  let store: Record<string, string> = {}
  return {
    getItem: vi.fn((key: string) => store[key] ?? null),
    setItem: vi.fn((key: string, value: string) => { store[key] = value }),
    removeItem: vi.fn((key: string) => { delete store[key] }),
    clear: vi.fn(() => { store = {} }),
  }
})()

Object.defineProperty(window, 'localStorage', { value: localStorageMock })

function renderHome() {
  return render(
    <MemoryRouter>
      <AppProvider>
        <Home />
      </AppProvider>
    </MemoryRouter>
  )
}

describe('Home Page', () => {
  beforeEach(() => {
    localStorageMock.clear()
    vi.clearAllMocks()
    mockFetch.mockResolvedValue({
      json: () => Promise.resolve({
        needs_setup: true,
        tips: [],
        token_usage: { calls_7d: 0, tokens_7d: 0, cost_7d: 0 },
      }),
    })
  })

  it('renders welcome message when user has no profile', () => {
    renderHome()
    expect(screen.getByText(/欢迎使用/i)).toBeInTheDocument()
  })

  it('renders onboarding step cards for new users', () => {
    renderHome()
    expect(screen.getByText('设置身份')).toBeInTheDocument()
    expect(screen.getByText('设计选题')).toBeInTheDocument()
    expect(screen.getByText('制作问卷')).toBeInTheDocument()
    expect(screen.getByText('开展调查')).toBeInTheDocument()
  })

  it('renders CTA button for identity setup', () => {
    renderHome()
    const cta = screen.getByText(/开始身份设置/)
    expect(cta).toBeInTheDocument()
    expect(cta.closest('button')).not.toBeNull()
  })

  it('does not show project dashboard when no profile', () => {
    renderHome()
    expect(screen.queryByText(/当前项目/)).not.toBeInTheDocument()
    expect(screen.queryByText(/光谱洞察/)).not.toBeInTheDocument()
  })
})
