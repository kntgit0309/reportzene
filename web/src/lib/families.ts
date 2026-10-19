// Product families with their own Etsy page; their product types live in the backend (app/services/families.py).
import type { FamilyKey } from './types'

export type Family = {
  key: FamilyKey
  name: string // "Ornament"
  plural: string // "ornaments", in sentences
  groupsNote: string // how the product types are made of trackingis sub product types
  planNote: string // how the plan sheet's categories map onto the product types
  accountParts: string // what a store opens onto in the by-account table
  accountsNote: string
}

export const FAMILIES: Record<FamilyKey, Family> = {
  ornament: {
    key: 'ornament', name: 'Ornament', plural: 'ornaments',
    groupsNote: 'Product types group trackingis sub product types (Wooden Garland is in Others).',
    planNote: 'Acrylic and Wood together are Acrylic + Wood, "Ornament khác" is Others.',
    accountParts: 'Product type',
    accountsNote: 'a store opens onto its product types. Actual: trackingis, ornament sub product types only, so the Felt pieces '
      + 'added by hand (not tied to a store) are not in these rows.',
  },
  shirt: {
    key: 'shirt', name: 'Shirt', plural: 'shirts',
    groupsNote: 'Shirt groups the trackingis sub product types listed under it.',
    planNote: 'T-shirt and Sweatshirt of the plan count together as Shirt.',
    accountParts: 'Sub product type',
    accountsNote: 'a store opens onto its sub product types, actuals only (the plan is for Shirt as a whole). Actual: trackingis, '
      + 'shirt sub product types only.',
  },
}
