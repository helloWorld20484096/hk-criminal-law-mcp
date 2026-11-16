# Vendored browser libraries

These files are vendored so the atlas works offline and has no third-party
runtime dependency.

| File | Package | Version | License |
|---|---|---|---|
| `regl-scatterplot.min.js` | [regl-scatterplot](https://github.com/flekschas/regl-scatterplot) | 1.16.0 | MIT |
| `regl.min.js` | [regl](https://github.com/regl-project/regl) | 2.1.1 | MIT |
| `pub-sub-es.esm.js` | [pub-sub-es](https://github.com/flekschas/pub-sub-es) | 3.0.0 | MIT |

`pub-sub-es.esm.js` is loaded as an ES module to set `window.createPubSub`
before the UMD scatterplot bundle loads.
