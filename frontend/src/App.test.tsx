import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import App from './App'

describe('MetaAnalyzer application shell', () => {
  it('renders the product introduction and foundation capabilities', () => {
    render(<App />)

    expect(screen.getByRole('heading', { name: /investigate metadata with confidence/i })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /investigation workspace/i })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /evidence analysis/i })).toBeInTheDocument()
  })
})
