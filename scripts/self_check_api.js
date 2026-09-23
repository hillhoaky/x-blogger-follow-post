#!/usr/bin/env node
// Offline checks: no tokens read, network calls, uploads, or writes to IFXData.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const helperPath = path.join(__dirname, 'vietnam_newsfeed_api.js');
const source = fs.readFileSync(helperPath, 'utf8');
const boundary = source.lastIndexOf('\nmain().catch(');
assert.ok(boundary > 0);
const moduleUnderTest = new Module(helperPath, module);
moduleUnderTest.filename = helperPath;
moduleUnderTest.paths = Module._nodeModulePaths(__dirname);
moduleUnderTest._compile(source.slice(0, boundary) + '\nmodule.exports = { getPost, postProblems, main, mockApi: fn => {api = fn;} };', helperPath);
const helper = moduleUnderTest.exports;
(async () => {
  let calls = [];
  helper.mockApi(async endpoint => {calls.push(endpoint); return {data:{id:123,language:'vn'}};});
  assert.equal((await helper.getPost(123)).language, 'vn');
  assert.deepEqual(calls, ['/feed/getFeedId?id=123']);
  helper.mockApi(async () => ({data:{id:123,language:'en'}}));
  await assert.rejects(helper.getPost(123), /not a Vietnam record/);
  const expected = {title:'Title',source:'Body',important:'1',labelId:20,remoteFiles:['https://example.test/1','https://example.test/2']};
  const post = {language:'vn',title:'Title',detail:'Body',important:true,newsfeedLabel:{id:20},fileUpload:JSON.stringify(expected.remoteFiles)};
  assert.deepEqual(helper.postProblems(post, expected).problems, []);
  assert.ok(helper.postProblems({...post,fileUpload:JSON.stringify([...expected.remoteFiles].reverse())},expected).problems.includes('image order'));
  assert.ok(helper.postProblems({...post,newsfeedLabel:undefined},expected).problems.includes('label'));
  calls = [];
  helper.mockApi(async endpoint => {calls.push(endpoint); throw Error('unexpected network call');});
  const originalArgs = process.argv;
  process.argv = ['node', helperPath, 'publish', '--task', '/nonexistent/test-task.json', '--apply'];
  try { await assert.rejects(helper.main(), /chat_preview/); } finally { process.argv = originalArgs; }
  assert.equal(calls.length, 0);
  console.log('Vietnam API checks passed: local route, language guard, label/media verification, preview-mode no-write guard.');
})().catch(error => {console.error(error.message);process.exitCode = 1;});
