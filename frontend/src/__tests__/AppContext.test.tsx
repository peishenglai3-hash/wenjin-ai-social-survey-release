import { describe, it, expect, beforeEach, vi } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { AppProvider, useApp } from '../context/AppContext'

// Mock API client
vi.mock('../api/client', () => ({
  default: {
    post: vi.fn(() => Promise.resolve({ data: {} })),
    get: vi.fn(() => Promise.resolve({ data: {} })),
  },
  setAccessToken: vi.fn(),
  getAccessToken: vi.fn(() => null),
}))

// Mock localStorage
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

describe('AppProvider', () => {
  beforeEach(() => {
    localStorageMock.clear()
    vi.clearAllMocks()
  })

  it('returns default theme "academic" with no saved state', () => {
    const { result } = renderHook(() => useApp(), {
      wrapper: ({ children }) => <AppProvider>{children}</AppProvider>,
    })

    expect(result.current.theme).toBe('academic')
    expect(result.current.profile).toBeNull()
    expect(result.current.project).toBeNull()
  })

  it('restores theme from localStorage on mount', () => {
    localStorageMock.getItem.mockImplementation((key: string): string => {
      if (key === 'app_theme') return 'government'
      return null as unknown as string
    })

    const { result } = renderHook(() => useApp(), {
      wrapper: ({ children }) => <AppProvider>{children}</AppProvider>,
    })

    expect(result.current.theme).toBe('government')
  })

  it('restores profile from localStorage on mount', () => {
    const savedProfile = JSON.stringify({
      id: 1, role: 'graduate',
      experience_level: 'intermediate',
      paradigm_preference: 'mixed',
    })
    localStorageMock.getItem.mockImplementation((key: string): string => {
      if (key === 'user_profile') return savedProfile
      return null as unknown as string
    })

    const { result } = renderHook(() => useApp(), {
      wrapper: ({ children }) => <AppProvider>{children}</AppProvider>,
    })

    expect(result.current.profile).not.toBeNull()
    expect(result.current.profile!.role).toBe('graduate')
  })

  it('setTheme updates state and persists to localStorage', () => {
    const { result } = renderHook(() => useApp(), {
      wrapper: ({ children }) => <AppProvider>{children}</AppProvider>,
    })

    act(() => { result.current.setTheme('youth') })

    expect(result.current.theme).toBe('youth')
    expect(localStorageMock.setItem).toHaveBeenCalledWith('app_theme', 'youth')
  })

  it('setProfile persists to localStorage', () => {
    const { result } = renderHook(() => useApp(), {
      wrapper: ({ children }) => <AppProvider>{children}</AppProvider>,
    })

    const profile = {
      id: 2, role: 'faculty', mode: 'academic', gender: null,
      experience_level: 'advanced', age_range: null, mbti: null,
      paradigm_preference: 'qualitative', scenario_preference: 'interview',
    }

    act(() => { result.current.setProfile(profile) })

    expect(result.current.profile).toEqual(profile)
    expect(localStorageMock.setItem).toHaveBeenCalledWith(
      'user_profile', JSON.stringify(profile)
    )
  })

  it('setProject persists project to localStorage', () => {
    const { result } = renderHook(() => useApp(), {
      wrapper: ({ children }) => <AppProvider>{children}</AppProvider>,
    })

    const project = {
      id: 1, title: '社区治理研究',
      research_direction: '基层治理', paradigm: 'qualitative',
      phase: 'pre_survey', status: 'active',
    }

    act(() => { result.current.setProject(project) })

    expect(result.current.project).toEqual(project)
    expect(localStorageMock.setItem).toHaveBeenCalledWith(
      'current_project', JSON.stringify(project)
    )
  })

  it('removes profile from localStorage when set to null', () => {
    const { result } = renderHook(() => useApp(), {
      wrapper: ({ children }) => <AppProvider>{children}</AppProvider>,
    })

    // Set first, then clear
    act(() => {
      result.current.setProfile({
        id: 1, role: 'undergraduate', mode: 'academic', gender: null,
        experience_level: 'beginner', age_range: null, mbti: null,
        paradigm_preference: 'quantitative', scenario_preference: 'survey',
      })
    })
    act(() => { result.current.setProfile(null) })

    expect(result.current.profile).toBeNull()
    expect(localStorageMock.removeItem).toHaveBeenCalledWith('user_profile')
  })
})
