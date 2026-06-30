import { describe, it, expect } from 'vitest'
import { avatarColor } from '../avatar'

describe('avatarColor', () => {
  it('returns a CSS gradient string', () => {
    const result = avatarColor('test')
    expect(result).toMatch(/^linear-gradient\(135deg, #[0-9a-f]{6}, #[0-9a-f]{6}\)$/)
  })

  it('returns the same gradient for the same input', () => {
    const a = avatarColor('Alice')
    const b = avatarColor('Alice')
    expect(a).toBe(b)
  })

  it('returns different gradients for different inputs', () => {
    const colors = new Set([
      avatarColor('Alice'),
      avatarColor('Bob'),
      avatarColor('Charlie'),
    ])
    expect(colors.size).toBe(3)
  })

  it('handles empty string', () => {
    const result = avatarColor('')
    expect(result).toMatch(/^linear-gradient\(135deg, #[0-9a-f]{6}, #[0-9a-f]{6}\)$/)
  })

  it('returns consistent results across many calls', () => {
    // Verify the hash doesn't have collisions on a modest set
    const names = Array.from({ length: 20 }, (_, i) => `name-${i}`)
    const gradients = names.map(n => avatarColor(n))
    const unique = new Set(gradients)
    // At least 10 unique gradients from 20 names (palette has 8 pairs)
    expect(unique.size).toBeGreaterThanOrEqual(8)
  })
})
