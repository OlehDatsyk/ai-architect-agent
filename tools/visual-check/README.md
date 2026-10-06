# Visual check

Takes desktop and mobile screenshots of the running app and audits each view with [axe-core](https://github.com/dequelabs/axe-core) (WCAG 2 A and AA, including colour contrast, plus best practices). It fails if there are accessibility violations or if the page scrolls sideways.

```bash
# with the backend and frontend running
cd tools/visual-check
npm install
npm run check                                   # http://127.0.0.1:5173, screenshots/ here
npm run check -- http://localhost:5173 /tmp/shots
```

It uses `@sparticuz/chromium`, a headless Chromium packaged inside an npm module, so it also runs where browser downloads are blocked. If a saved project exists, the first one is opened and checked too.
