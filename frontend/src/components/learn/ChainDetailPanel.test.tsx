/**
 * ChainDetailPanel.test.tsx — Ficha educativa de una blockchain.
 *
 * Verifica el estado vacío y que, al seleccionar una cadena, se muestran sus
 * datos y al menos una de sus conexiones.
 */

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import ChainDetailPanel from './ChainDetailPanel'

describe('ChainDetailPanel', () => {
  it('muestra un estado guía cuando no hay cadena seleccionada', () => {
    render(<ChainDetailPanel selected={null} />)
    expect(screen.getByText('Explora el ecosistema')).toBeInTheDocument()
  })

  it('muestra los datos de la cadena seleccionada', () => {
    render(<ChainDetailPanel selected="ethereum" />)
    expect(screen.getByText('Ethereum')).toBeInTheDocument()
    expect(screen.getAllByText(/Proof of Stake/).length).toBeGreaterThan(0)
    // Ethereum tiene conexiones (puentes + L2 que liquidan en él)
    expect(screen.getByText(/Conexiones/)).toBeInTheDocument()
  })

  it('marca una L2 con su cadena de liquidación', () => {
    render(<ChainDetailPanel selected="arbitrum" />)
    expect(screen.getByText('Arbitrum')).toBeInTheDocument()
    expect(screen.getAllByText(/liquida en Ethereum/).length).toBeGreaterThan(0)
  })
})
