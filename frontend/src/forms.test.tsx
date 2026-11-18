// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from './api'
import { Editor } from './forms'

afterEach(cleanup)

describe('field-level editor', () => {
  it('sends only changed fields and counts UTF-8 bytes', async () => {
    const save = vi.fn(async () => {})
    render(<Editor fields={[{ key: 'notes', kind: 'notes', help: 'Capacity' }, { key: 'active', kind: 'boolean' }]}
      initial={{ notes: null, active: true }} onCancel={() => {}} onSave={save} />)
    fireEvent.change(screen.getByLabelText('Notes'), { target: { value: 'é' } })
    expect(screen.getByText(new RegExp('4.?094 UTF-8 bytes remaining'))).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))
    await waitFor(() => expect(save).toHaveBeenCalledWith({
      changes: { notes: 'é' }, expected: { notes: null, active: true }, overwrite: false,
    }))
  })

  it('shows the conflicting values and provides an explicit overwrite', async () => {
    const save = vi.fn().mockRejectedValueOnce(new ApiError(409, {
      fields: { notes: { current: 'Current notes', proposed: 'New notes' } },
    })).mockResolvedValueOnce(undefined)
    render(<Editor fields={[{ key: 'notes', kind: 'notes' }]} initial={{ notes: 'Old notes' }} onCancel={() => {}} onSave={save} />)
    fireEvent.change(screen.getByLabelText('Notes'), { target: { value: 'New notes' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))
    expect(await screen.findByText(/Current: Current notes · Yours: New notes/)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Overwrite changed fields' }))
    await waitFor(() => expect(save).toHaveBeenLastCalledWith({
      changes: { notes: 'New notes' }, expected: { notes: 'Old notes' }, overwrite: true,
    }))
  })
})
