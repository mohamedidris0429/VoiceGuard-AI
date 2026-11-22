import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { BandEnergyBars, InteractiveWaveform, RmsTimeline } from '../components/forensics'

describe('forensics visualisations', () => {
  it('renders relative energy for each frequency band', () => {
    render(
      <BandEnergyBars
        bands={[
          { label: '0–250 Hz', low_hz: 0, high_hz: 250, share: 0.42 },
          { label: '250–500 Hz', low_hz: 250, high_hz: 500, share: 0.18 },
        ]}
      />,
    )
    expect(screen.getByRole('img', { name: /relative energy by frequency band/i })).toBeTruthy()
    expect(screen.getByText('42.0%')).toBeTruthy()
    expect(screen.getByText('18.0%')).toBeTruthy()
  })

  it('renders the RMS timeline with its point count', () => {
    render(<RmsTimeline times={[0, 1, 2]} values={[0.1, 0.9, 0.3]} />)
    expect(screen.getByRole('img', { name: /rms energy over time/i })).toBeTruthy()
    expect(screen.getByText(/3 points/)).toBeTruthy()
  })

  it('renders the interactive waveform and seeks on click', () => {
    const onSeek = vi.fn()
    render(<InteractiveWaveform peaks={[0.2, 0.8, 0.4, 0.1]} duration={4} onSeek={onSeek} />)

    const canvas = screen.getByRole('img', { name: /interactive audio waveform/i })
    // jsdom has no layout engine, so provide a deterministic bounding box.
    canvas.getBoundingClientRect = () => ({
      left: 0,
      top: 0,
      width: 200,
      height: 128,
      right: 200,
      bottom: 128,
      x: 0,
      y: 0,
      toJSON() {},
    })

    fireEvent.click(canvas, { clientX: 100 })
    expect(onSeek).toHaveBeenCalledWith(2)
    expect(screen.getByText(/click the waveform/i)).toBeTruthy()
  })
})
