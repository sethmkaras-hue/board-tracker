import type { Page } from '@playwright/test'

export async function fillReviewDates(page: Page, date = '2026-05-15') {
  const inputs = page.getByRole('dialog').getByLabel('Review date *', {exact:true})
  for (const input of await inputs.all()) await input.fill(date)
}
