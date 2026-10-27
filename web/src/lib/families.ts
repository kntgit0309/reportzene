// Product families with their own Etsy page; their product types live in the backend (app/services/families.py).
// Adding one: an entry here (the route, the Etsy menu item and its Settings › Plan picker follow) and one in the backend.
import type { Component } from 'vue'
import { Box, Flag, Grid, Postcard, Present, ShoppingBag } from '@element-plus/icons-vue'
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
  quilted: {
    key: 'quilted', name: 'Quilted', plural: 'quilted goods', icon: ShoppingBag,
    groupsNote: 'Product types are named as in KH Quilted, each one trackingis sub product type: Quilted Tote Bag, Quilted Laundry '
      + 'Basket, Quilted Weekend Bag and Quilted Table Runner.',
    planNote: 'The categories of the plan are the product types of the same name (the sheet\'s "Laudry" and "Weeken" spellings count too).',
    planSheetHint: 'The "KH Quilted" tab (sheet "Quilted"), same layout as KH Blanket: a "Shop Name | Team" label row, then per month a '
      + '"Total" column and the 4 categories (Quilted Tote Bag, Laundry Basket, Weekend Bag, Table Runner), in pieces.',
    accountParts: 'Product type',
    accountsNote: 'a store opens onto its product types. Actual: trackingis, quilted sub product types only.',
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
  wooden_block: {
    key: 'wooden_block', name: 'Wooden Block', plural: 'wooden blocks', icon: Box,
    groupsNote: 'Wooden Block groups the trackingis sub product types listed under it.',
    planNote: 'KH Wooden Block has one value per month, for Wooden Block as a whole.',
    planSheetHint: 'The "KH Wooden Block" tab: a "Shop Name | Team | … | MM-YYYY" header row, one column per month (no categories), in pieces.',
    accountParts: 'Sub product type',
    accountsNote: 'a store opens onto its sub product types, actuals only (the plan is for Wooden Block as a whole). Actual: '
      + 'trackingis, wooden block sub product types only.',
  },
  badge_reel: {
    key: 'badge_reel', name: 'Badge Reel', plural: 'badge reels', icon: Postcard,
    groupsNote: 'Badge Reel groups the trackingis sub product types listed under it.',
    planNote: 'KH Badge Reel has one Total per month, for Badge Reel as a whole.',
    planSheetHint: 'The "KH Badge Reel" tab: same layout as KH Flag, a "Total" column per month (no categories), in pieces.',
    accountParts: 'Sub product type',
    accountsNote: 'a store opens onto its sub product types, actuals only (the plan is for Badge Reel as a whole). Actual: '
      + 'trackingis, badge reel sub product types only.',
  },
  others: {
    key: 'others', name: 'Others', plural: 'other products', icon: Grid,
    groupsNote: 'Sticker, Scrub cap, Fabric Welcome Sign and Baseball Jersey are the products of KH SP khác; Other products takes '
      + 'every trackingis sub product type no other report covers (new ones too), its rows per trackingis product type.',
    planNote: 'KH SP khác plans per product for ZenE as a whole, so it only compares with all ZenE teams and stores.',
    planSheetHint: 'The "Others" tab (sheet "KH SP khác"): "Product | PL2/item | … | MM-YYYY", one row per product; the first block '
      + 'of months is the sales per month, in pieces.',
    accountParts: 'Product type',
    accountsNote: 'a store opens onto its product types, actuals only (KH SP khác has no per-store plan). Actual: trackingis, '
      + 'the sub product types of this page only.',
  },
}
export const FAMILY_LIST = Object.values(FAMILIES)
