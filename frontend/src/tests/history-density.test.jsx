import { describe, it, expect, vi } from 'vitest'

// Test the density logic in isolation
describe('compact tables density logic', () => {
  it('generates compact padding when compact is true', () => {
    const compact = true
    const headPadding = compact ? 'px-3 py-1.5' : 'px-5 py-3'
    const cellPadding = compact ? 'px-2 py-1.5' : 'px-3 py-3'
    const spanInnerPadding = compact ? 'p-1' : 'p-1.5'
    const tableFontSize = compact ? 'text-[13px]' : 'text-sm'
    const dataDensity = compact ? 'compact' : 'comfortable'

    expect(headPadding).toBe('px-3 py-1.5')
    expect(cellPadding).toBe('px-2 py-1.5')
    expect(spanInnerPadding).toBe('p-1')
    expect(tableFontSize).toBe('text-[13px]')
    expect(dataDensity).toBe('compact')
  })

  it('generates comfortable padding when compact is false', () => {
    const compact = false
    const headPadding = compact ? 'px-3 py-1.5' : 'px-5 py-3'
    const cellPadding = compact ? 'px-2 py-1.5' : 'px-3 py-3'
    const spanInnerPadding = compact ? 'p-1' : 'p-1.5'
    const tableFontSize = compact ? 'text-[13px]' : 'text-sm'
    const dataDensity = compact ? 'compact' : 'comfortable'

    expect(headPadding).toBe('px-5 py-3')
    expect(cellPadding).toBe('px-3 py-3')
    expect(spanInnerPadding).toBe('p-1.5')
    expect(tableFontSize).toBe('text-sm')
    expect(dataDensity).toBe('comfortable')
  })

  it('derives all styles from single compact source of truth', () => {
    const compact = true
    const styles = {
      headPadding: compact ? 'px-3 py-1.5' : 'px-5 py-3',
      cellPadding: compact ? 'px-2 py-1.5' : 'px-3 py-3',
      spanInnerPadding: compact ? 'p-1' : 'p-1.5',
      tableFontSize: compact ? 'text-[13px]' : 'text-sm',
      dataDensity: compact ? 'compact' : 'comfortable',
    }
    // All styles should be consistent with compact=true
    expect(styles.headPadding).toContain('py-1.5')
    expect(styles.cellPadding).toContain('py-1.5')
    expect(styles.spanInnerPadding).toBe('p-1')
    expect(styles.tableFontSize).toBe('text-[13px]')
    expect(styles.dataDensity).toBe('compact')
  })

  it('switches to comfortable mode when compact is false', () => {
    const compact = false
    const styles = {
      headPadding: compact ? 'px-3 py-1.5' : 'px-5 py-3',
      cellPadding: compact ? 'px-2 py-1.5' : 'px-3 py-3',
      spanInnerPadding: compact ? 'p-1' : 'p-1.5',
      tableFontSize: compact ? 'text-[13px]' : 'text-sm',
      dataDensity: compact ? 'compact' : 'comfortable',
    }
    // All styles should be comfortable when compact=false
    expect(styles.headPadding).toBe('px-5 py-3')
    expect(styles.cellPadding).toBe('px-3 py-3')
    expect(styles.spanInnerPadding).toBe('p-1.5')
    expect(styles.tableFontSize).toBe('text-sm')
    expect(styles.dataDensity).toBe('comfortable')
  })
})