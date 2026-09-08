const assert = require("node:assert/strict");
const {readFileSync} = require("node:fs");
const {join} = require("node:path");
const {test} = require("node:test");
const vm = require("node:vm");

function workshop() {
  const source = readFileSync(join(__dirname, "../web/loop.js"), "utf8");
  const nodes = new Map(), frames = [], requests = [], classes = new Set();
  const context = vm.createContext({
    document: {
      getElementById(id) {
        if (!nodes.has(id)) nodes.set(id, {setAttribute() {}});
        return nodes.get(id);
      },
      body: {classList: {toggle(name, on) {on ? classes.add(name) : classes.delete(name);}}},
    },
    requestAnimationFrame: callback => frames.push(callback),
    setTimeout() {}, clearTimeout() {},
    requests,
  });
  // Load the workshop controller before its DOM listener/bootstrap section.
  vm.runInContext(source.slice(0, source.indexOf('el("canvas").addEventListener("launchrequest"')), context);
  vm.runInContext(`
    render = renderScope = syncStatus = () => {};
    api = async (path, payload) => { requests.push(payload.selection); return {}; };
    scene = {fit() {selectModel({kind:"ship", expanded:true});}};
  `, context);
  return {
    run: code => vm.runInContext(code, context),
    async settle() {
      // Bound the drain so the former fit -> selection -> fit loop fails safely.
      for (let i = 0; i < 5 && frames.length; i++) frames.shift()();
      await vm.runInContext("selectionSync", context);
      assert.equal(frames.length, 0, "selection must not schedule an endless view reset");
    },
    requests, classes,
  };
}

test("torpedo selection survives the automatic sidebar collapse", async () => {
  const page = workshop();
  page.run('selectModel({kind:"torpedo", id:"torpedo_02"})');
  await page.settle();
  assert.equal(page.run("selectedTorpedo"), "torpedo_02");
  assert.equal(page.classes.has("presentation"), true);
  assert.deepEqual(JSON.parse(JSON.stringify(page.requests)), [{kind:"torpedo", id:"torpedo_02"}]);
});

test("expanding the sidebar preserves the selected torpedo", async () => {
  const page = workshop();
  page.run('selectModel({kind:"torpedo", id:"torpedo_01"})');
  await page.settle();
  page.run("setPresentation(false)");
  await page.settle();
  assert.equal(page.run("selectedTorpedo"), "torpedo_01");
  assert.equal(page.classes.has("presentation"), false);
  assert.equal(page.requests.length, 1);
});

test("returning to the ship syncs the cleared selection once", async () => {
  const page = workshop();
  page.run('selectModel({kind:"torpedo", id:"torpedo_01"})');
  await page.settle();
  page.run('selectModel({kind:"ship", expanded:false})');
  await page.settle();
  assert.equal(page.run("selectedTorpedo"), null);
  assert.equal(page.classes.has("presentation"), false);
  assert.equal(page.requests.length, 2);
});
