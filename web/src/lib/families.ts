// Product families with their own Etsy page; their product types live in the backend (app/services/families.py).
// Adding one: an entry here (the route, the Etsy menu item and its Settings › Plan picker follow) and one in the backend.
import type { Component } from 'vue'
import { Flag, Present } from '@element-plus/icons-vue'
import BlanketIcon from '../components/icons/BlanketIcon.vue'
import ShirtIcon from '../components/icons/ShirtIcon.vue'
import type { FamilyKey } from './types'

export type Family = {
  key: FamilyKey
  name: string // "Ornament"
  plural: string // "ornaments", in sentences
  icon: Component // Etsy menu
  groupsNote: string // how the product types are made of trackingis sub product types
  planNote: string // how the plan sheet's categories map onto the product types
  planSheetHint: string // Settings › Plan
  accountParts: string // what a store opens onto in the by-account table
  accountsNote: string
}

export const FAMILIES: Record<FamilyKey, Family> = {
  ornament: {
    key: 'ornament', name: 'Ornament', plural: 'ornaments', icon: Present,
    groupsNote: 'Product types group trackingis sub product types (Wooden Garland is in Others).',
    planNote: 'Acrylic and Wood together are Acrylic + Wood, "Ornament khác" is Others.',
    planSheetHint: 'The "KH Ornament" tab: a "Shop Name | Team" label row, then per month a "Total" column and the categories, in pieces.',
    accountParts: 'Product type',
    accountsNote: 'a store opens onto its product types. Actual: trackingis, ornament sub product types only, so the Felt pieces '
      + 'added by hand (not tied to a store) are not in these rows.',
  },
  shirt: {
    key: 'shirt', name: 'Shirt', plural: 'shirts', icon: ShirtIcon,
    groupsNote: 'Shirt groups the trackingis sub product types listed under it.',
    planNote: 'T-shirt and Sweatshirt of the plan count together as Shirt.',
    planSheetHint: 'The "KH Shirt" tab, same layout; its T-shirt and Sweatshirt columns count together as Shirt.',
    accountParts: 'Sub product type',
    accountsNote: 'a store opens onto its sub product types, actuals only (the plan is for Shirt as a whole). Actual: trackingis, '
      + 'shirt sub product types only.',
  },
  blanket: {
    key: 'blanket', name: 'Blanket', plural: 'blankets', icon: BlanketIcon,
    groupsNote: 'Product types are named as in KH Blanket, each one trackingis sub product type (Velveteen is "Blanket").',
    planNote: 'Velveteen, Woven and Quilted of the plan are the product types of the same name.',
    planSheetHint: 'The "KH Blanket" tab, same layout; its Velveteen, Woven and Quilted columns are the product types.',
    accountParts: 'Product type',
    accountsNote: 'a store opens onto its product types. Actual: trackingis, blanket sub product types only.',
  },
  flag: {
    key: 'flag', name: 'Flag', plural: 'flags', icon: Flag,
    groupsNote: 'Flag groups the trackingis sub product types listed under it.',
    planNote: 'KH Flag has one Total per month, for Flag as a whole.',
    planSheetHint: 'The "KH Flag" tab: a "Shop Name | Team" label row, then per month a "Total" column only (no categories), in pieces.',
    accountParts: 'Sub product type',
    accountsNote: 'a store opens onto its sub product types, actuals only (the plan is for Flag as a whole). Actual: trackingis, '
      + 'flag sub product types only.',
  },
}
export const FAMILY_LIST = Object.values(FAMILIES)
