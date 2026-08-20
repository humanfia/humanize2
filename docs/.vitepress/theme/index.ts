// The features landing is a set of diagrams rather than a page of prose, each feature page is
// one diagram of its own, and every flow has its loop played on its own page -- so the theme
// exists to register them. Everything else is VitePress's default theme untouched: the guides,
// tutorials and reference render exactly as they did.
import type { Theme } from 'vitepress'
import DefaultTheme from 'vitepress/theme'

import HmzAccounts from './components/HmzAccounts.vue'
import HmzAnchor from './components/HmzAnchor.vue'
import HmzBackends from './components/HmzBackends.vue'
import HmzDaemon from './components/HmzDaemon.vue'
import HmzFeatures from './components/HmzFeatures.vue'
import HmzFlowShape from './components/HmzFlowShape.vue'
import HmzFlows from './components/HmzFlows.vue'
import HmzGallery from './components/HmzGallery.vue'
import HmzGoal from './components/HmzGoal.vue'
import HmzInstall from './components/HmzInstall.vue'
import HmzLoops from './components/HmzLoops.vue'
import HmzMap from './components/HmzMap.vue'
import HmzMoments from './components/HmzMoments.vue'
import HmzOrchestra from './components/HmzOrchestra.vue'
import HmzPerson from './components/HmzPerson.vue'
import HmzProphecy from './components/HmzProphecy.vue'
import HmzResume from './components/HmzResume.vue'
import HmzShape from './components/HmzShape.vue'
import HmzStack from './components/HmzStack.vue'
import HmzSteer from './components/HmzSteer.vue'
import HmzSyscalls from './components/HmzSyscalls.vue'
import HmzSurfaces from './components/HmzSurfaces.vue'
import HmzTimeline from './components/HmzTimeline.vue'
import HmzTurns from './components/HmzTurns.vue'
import './style.css'

export default {
  extends: DefaultTheme,
  enhanceApp({ app }) {
    app.component('HmzAccounts', HmzAccounts)
    app.component('HmzAnchor', HmzAnchor)
    app.component('HmzBackends', HmzBackends)
    app.component('HmzDaemon', HmzDaemon)
    app.component('HmzFeatures', HmzFeatures)
    app.component('HmzFlowShape', HmzFlowShape)
    app.component('HmzFlows', HmzFlows)
    app.component('HmzGallery', HmzGallery)
    app.component('HmzGoal', HmzGoal)
    app.component('HmzInstall', HmzInstall)
    app.component('HmzLoops', HmzLoops)
    app.component('HmzMap', HmzMap)
    app.component('HmzMoments', HmzMoments)
    app.component('HmzOrchestra', HmzOrchestra)
    app.component('HmzPerson', HmzPerson)
    app.component('HmzProphecy', HmzProphecy)
    app.component('HmzResume', HmzResume)
    app.component('HmzShape', HmzShape)
    app.component('HmzStack', HmzStack)
    app.component('HmzSteer', HmzSteer)
    app.component('HmzSyscalls', HmzSyscalls)
    app.component('HmzSurfaces', HmzSurfaces)
    app.component('HmzTimeline', HmzTimeline)
    app.component('HmzTurns', HmzTurns)
  },
} satisfies Theme
