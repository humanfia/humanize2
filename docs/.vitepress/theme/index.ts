// The home page is a set of diagrams rather than a page of prose, so the theme exists to
// register them. Everything else is VitePress's default theme untouched: the guides,
// tutorials and reference render exactly as they did before.
import type { Theme } from 'vitepress'
import DefaultTheme from 'vitepress/theme'

import HmzAnchor from './components/HmzAnchor.vue'
import HmzFeatures from './components/HmzFeatures.vue'
import HmzGallery from './components/HmzGallery.vue'
import HmzInstall from './components/HmzInstall.vue'
import HmzOrchestra from './components/HmzOrchestra.vue'
import HmzStack from './components/HmzStack.vue'
import './style.css'

export default {
  extends: DefaultTheme,
  enhanceApp({ app }) {
    app.component('HmzAnchor', HmzAnchor)
    app.component('HmzFeatures', HmzFeatures)
    app.component('HmzGallery', HmzGallery)
    app.component('HmzInstall', HmzInstall)
    app.component('HmzOrchestra', HmzOrchestra)
    app.component('HmzStack', HmzStack)
  },
} satisfies Theme
