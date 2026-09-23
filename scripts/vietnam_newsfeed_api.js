#!/usr/bin/env node
// Vietnam route adaptation of x-newsfeed-post helper; source SHA256: bb006f561b0c5d72ccf31a47168e9683fcc3f7743815293063d9d067b9abc461

const crypto = require('crypto');
const fs = require('fs');
const os = require('os');
const path = require('path');
const BASE_SKILL = path.join(os.homedir(), '.codex/skills/x-newsfeed-post');
const { readLatest } = require(path.join(BASE_SKILL, 'scripts/chrome_localstorage'));
const OPERATIONS_FILE = path.join(__dirname, '..', 'references/sources.json');

const API_BASE = 'https://api.ifxdata.com/api/v1/admin';
const TOKEN_KEY = '_https://admin.ifxdata.com\0\x01accessToken';
const USER_KEY = '_https://admin.ifxdata.com\0\x01user';
const IMAGE1_FOOTER = path.join(BASE_SKILL, 'assets', 'image1-footer-1980x302.png');
const IMAGE1_FOOTER_SHA256 = '4c34b5de6f45cee6e3cc3299199784e67a2aae7e7e168aecdb44c030b279b608';
const IMAGE1_STYLE_VERSION = 'image1-1980-v1';
const NONE_STYLE_VERSION = 'none-v1';
const POSTER_WIDTH = 1980;
const IMAGE1_FOOTER_HEIGHT = 302;
const IMAGE1_GRADIENT_HEIGHT = 180;
const RECENT_DUPLICATE_PAGES = 5;
const PAGE_SIZE = 100;
const READBACK_DELAYS_MS = [0, 300, 900, 1800];
let cachedStorage = null;
let cachedToken = null;
let cachedUser = null;
let image1AssetValidated = false;

function parseArgs(argv) {
  const command = argv[0];
  const values = {};
  for (let index = 1; index < argv.length; index += 1) {
    const item = argv[index];
    if (!item.startsWith('--')) throw new Error(`Unexpected argument: ${item}`);
    const key = item.slice(2);
    if (['apply', 'verbose', 'allow-duplicate-media'].includes(key)) {
      values[key] = true;
      continue;
    }
    const value = argv[index + 1];
    if (!value || value.startsWith('--')) throw new Error(`Missing value for --${key}`);
    values[key] = value;
    index += 1;
  }
  return { command, values };
}

function required(values, key) {
  if (!values[key]) throw new Error(`--${key} is required`);
  return values[key];
}

function localStorageValue(key) {
  if (!cachedStorage) cachedStorage = readLatest();
  const record = cachedStorage.get(key);
  if (!record || record.valueType !== 1) throw new Error(`Browser localStorage value not found: ${key.split('\x01').pop()}`);
  let value = record.value;
  if (value[0] === 1) value = value.subarray(1);
  return value.toString('utf8');
}

function accessToken() {
  if (!cachedToken) cachedToken = localStorageValue(TOKEN_KEY);
  return cachedToken;
}

function currentUser() {
  if (!cachedUser) {
    const user = JSON.parse(localStorageValue(USER_KEY));
    if (!Number.isInteger(user.id)) throw new Error('Authenticated IFXData user id is unavailable');
    cachedUser = { id: user.id, nickname: user.nickname || null };
  }
  return cachedUser;
}

async function api(endpoint, options = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 30000);
  const isForm = options.body instanceof FormData;
  try {
    const response = await fetch(`${API_BASE}${endpoint}`, {
      ...options,
      signal: controller.signal,
      headers: {
        Authorization: `Bearer ${accessToken()}`,
        ...(isForm ? {} : { 'Content-Type': 'application/json' }),
        ...(options.headers || {}),
      },
    });
    const body = await response.json();
    if (!response.ok || body.code !== 0) {
      throw new Error(`IFXData API error ${response.status}: ${body.msg || JSON.stringify(body)}`);
    }
    return body;
  } finally {
    clearTimeout(timer);
  }
}

function rows(body) {
  const value = body?.data?.data ?? body?.data ?? [];
  return Array.isArray(value) ? value : [];
}

async function getPost(id) {
  const result = await api(`/feed/getFeedId?id=${encodeURIComponent(id)}`);
  if (!result.data || !result.data.id) throw new Error(`Newsfeed ${id} was not found`);
  if (result.data.language !== 'vn') throw new Error('Readback is not a Vietnam record');
  return result.data;
}

async function recentPosts(pageNum) {
  const query = new URLSearchParams({ country: 'vn', pageNum: String(pageNum), pageSize: String(PAGE_SIZE) });
  return rows(await api(`/feed/getAll?${query}`));
}

async function findExactTitle(title, excludeId = null) {
  for (let pageNum = 1; pageNum <= RECENT_DUPLICATE_PAGES; pageNum += 1) {
    const page = await recentPosts(pageNum);
    const match = page.find((row) => row.title === title && Number(row.id) !== Number(excludeId));
    if (match) return match;
    if (page.length < PAGE_SIZE) break;
  }
  return null;
}

async function resolveLabel(name) {
  if (typeof name !== 'string' || !name.trim()) throw new Error('Task label is required');
  name = name.trim();
  const query = new URLSearchParams({ language: 'en', type: '1', pageNum: '1', pageSize: '1000', name });
  const match = rows(await api(`/feed/getNewsfeedLabel?${query}`)).find((row) => row.name === name);
  if (!match) throw new Error(`Global Newsfeed label not found: ${name}`);
  return match;
}

function loadTask(taskPath) {
  const resolved = path.resolve(taskPath);
  const task = JSON.parse(fs.readFileSync(resolved, 'utf8'));
  if (task.admin_scope !== 'vn' || task.target_language !== 'vi') throw new Error('Task must explicitly target vi in vn scope');
  return { task, taskPath: resolved };
}

function bodyFromTask(task, fallback = null) {
  const body = task.body ?? task.source ?? fallback;
  if (typeof body !== 'string' || !body.trim()) throw new Error('Task body is required');
  return body.replace(/\n\n/gi, '\n');
}

function importantValue(value) {
  if (value === true || value === 1) return '1';
  if (value === false || value === 0) return '0';
  const normalized = String(value).trim().toLowerCase();
  if (['yes', 'true', '1'].includes(normalized)) return '1';
  if (['no', 'false', '0'].includes(normalized)) return '0';
  throw new Error(`Task important must be Yes/No, true/false, or 1/0; received: ${value}`);
}

function targetCountry(task) {
  const value = String(task.target_language || 'vi').toLowerCase();
  if (!['vi', 'vn', 'vietnam'].includes(value)) throw new Error(`Unsupported Newsfeed target language: ${value}`);
  return 'vn';
}

function sha256(filePath) {
  return crypto.createHash('sha256').update(fs.readFileSync(filePath)).digest('hex');
}

function sha256Text(value) {
  return crypto.createHash('sha256').update(value).digest('hex');
}

function imageStyle(task) {
  const value = String(task.image_style || 'Image1').trim().toLowerCase();
  if (value === 'image1') return { name: 'Image1', version: IMAGE1_STYLE_VERSION };
  if (value === 'none') return { name: 'None', version: NONE_STYLE_VERSION };
  throw new Error(`API poster rendering supports Image1 or None, not ${task.image_style}; use the admin UI fallback`);
}

function orderedImages(task, values) {
  const images = Array.isArray(task.images) ? [...task.images] : [];
  images.sort((left, right) => Number(left.index) - Number(right.index));
  const expected = Number(task.source_image_count ?? images.length);
  if (expected !== images.length) throw new Error(`Image count mismatch: expected ${expected}, found ${images.length}`);
  const seenIndexes = new Set();
  const seenHashes = new Map();
  const result = images.map((item, offset) => {
    const index = Number(item.index);
    if (index !== offset + 1 || seenIndexes.has(index)) throw new Error('Image indexes must be unique and consecutive from 1');
    seenIndexes.add(index);
    const filePath = path.resolve(item.path || item.output_path || '');
    if (!filePath || !fs.statSync(filePath, { throwIfNoEntry: false })?.isFile()) throw new Error(`Image ${index} is missing: ${filePath}`);
    const hash = sha256(filePath);
    const prior = seenHashes.get(hash);
    if (prior && !(task.allow_duplicate_media || values['allow-duplicate-media'])) {
      throw new Error(`Images ${prior} and ${index} are identical; upload blocked`);
    }
    seenHashes.set(hash, index);
    return { index, path: filePath, sha256: hash };
  });
  return result;
}

function loadSharp() {
  const candidates = [
    'sharp',
    path.join(os.homedir(), '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/sharp'),
  ];
  for (const candidate of candidates) {
    try {
      return require(candidate);
    } catch (error) {
      if (candidate === candidates[candidates.length - 1]) throw new Error('Sharp is unavailable; use the bundled Codex Node.js runtime');
    }
  }
}

async function validateReadableImages(images) {
  const sharp = loadSharp();
  const supported = new Set(['jpeg', 'png', 'webp', 'gif', 'tiff', 'avif']);
  const mimeByFormat = {
    jpeg: 'image/jpeg',
    png: 'image/png',
    webp: 'image/webp',
    gif: 'image/gif',
    tiff: 'image/tiff',
    avif: 'image/avif',
  };
  const result = [];
  for (const image of images) {
    let metadata;
    try {
      metadata = await sharp(image.path).metadata();
    } catch (error) {
      throw new Error(`Image ${image.index} is unreadable: ${image.path}`);
    }
    if (!supported.has(metadata.format) || !metadata.width || !metadata.height) {
      throw new Error(`Image ${image.index} has an unsupported or invalid format: ${metadata.format || 'unknown'}`);
    }
    result.push({ ...image, format: metadata.format, mime: mimeByFormat[metadata.format] });
  }
  return result;
}

function verifyImage1Asset() {
  if (image1AssetValidated) return;
  if (!fs.existsSync(IMAGE1_FOOTER)) throw new Error(`Image1 footer asset is missing: ${IMAGE1_FOOTER}`);
  const actual = sha256(IMAGE1_FOOTER);
  if (actual !== IMAGE1_FOOTER_SHA256) {
    throw new Error(`Image1 footer asset checksum mismatch: expected ${IMAGE1_FOOTER_SHA256}, found ${actual}`);
  }
  image1AssetValidated = true;
}

async function renderImage1(inputPath, outputPath) {
  verifyImage1Asset();
  const sharp = loadSharp();
  const { data: resized, info } = await sharp(inputPath)
    .rotate()
    .resize({ width: POSTER_WIDTH })
    .flatten({ background: '#e8e8e8' })
    .png()
    .toBuffer({ resolveWithObject: true });
  const gradientHeight = Math.min(IMAGE1_GRADIENT_HEIGHT, info.height);
  const gradient = Buffer.from(`<svg width="${POSTER_WIDTH}" height="${gradientHeight}" xmlns="http://www.w3.org/2000/svg"><defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset="0.3" stop-color="#fff" stop-opacity="0.6"/><stop offset="1" stop-color="#e8e8e8" stop-opacity="1"/></linearGradient></defs><rect width="100%" height="100%" fill="url(#g)"/></svg>`);
  const faded = await sharp(resized)
    .composite([{ input: gradient, left: 0, top: info.height - gradientHeight }])
    .png()
    .toBuffer();
  await sharp({ create: { width: POSTER_WIDTH, height: info.height + IMAGE1_FOOTER_HEIGHT, channels: 3, background: '#e8e8e8' } })
    .composite([
      { input: faded, left: 0, top: 0 },
      { input: IMAGE1_FOOTER, left: 0, top: info.height },
    ])
    .jpeg({ quality: 92 })
    .toFile(outputPath);
  return outputPath;
}

async function prepareUploadFiles(task, images, outputDir) {
  const style = imageStyle(task);
  if (style.name === 'None') {
    return images.map((image) => ({
      index: image.index,
      sourcePath: image.path,
      sourceSha256: image.sha256,
      path: image.path,
      renderedSha256: image.sha256,
      mime: image.mime,
    }));
  }
  fs.mkdirSync(outputDir, { recursive: true });
  const result = [];
  for (const image of images) {
    const outputPath = path.join(outputDir, `image${image.index}-image1.jpg`);
    await renderImage1(image.path, outputPath);
    result.push({
      index: image.index,
      sourcePath: image.path,
      sourceSha256: image.sha256,
      path: outputPath,
      renderedSha256: sha256(outputPath),
      mime: 'image/jpeg',
    });
  }
  return result;
}

async function uploadFile(file) {
  const form = new FormData();
  form.append('file', new Blob([fs.readFileSync(file.path)], { type: file.mime }), path.basename(file.path));
  const result = await api('/uploadFile', { method: 'POST', body: form });
  const remotePath = result.path ?? result.data?.path;
  if (typeof remotePath !== 'string' || !remotePath.startsWith('http')) throw new Error('Upload response did not include a remote path');
  return remotePath;
}

function parseRemoteFiles(post) {
  try {
    const value = JSON.parse(post.fileUpload || '[]');
    return Array.isArray(value) ? value : [];
  } catch (error) {
    throw new Error(`Newsfeed ${post.id} has invalid fileUpload JSON`);
  }
}

function remoteImportantValue(value) {
  return value === true || value === 1 || String(value).trim().toLowerCase() === 'true' || String(value).trim() === '1' ? '1' : '0';
}

function normalizedCopy(value) {
  return String(value || '')
    .normalize('NFKC')
    .replace(/[“”‘’"']/g, '')
    .replace(/\s+/g, ' ')
    .trim();
}

function postProblems(post, expected, mediaMode = 'urls', copyMode = 'strict') {
  const remoteFiles = parseRemoteFiles(post);
  const problems = [];
  if (post.language !== 'vn') problems.push('Vietnam language');
  if (post.title !== expected.title) problems.push('title');
  const bodyMatches = copyMode === 'loose'
    ? normalizedCopy(post.detail) === normalizedCopy(expected.source)
    : post.detail === expected.source;
  if (!bodyMatches) problems.push('body');
  if (remoteImportantValue(post.important) !== expected.important) problems.push('important');
  if (Number(post.newsfeedLabel?.id) !== Number(expected.labelId)) problems.push('label');
  if (mediaMode === 'urls' && JSON.stringify(remoteFiles) !== JSON.stringify(expected.remoteFiles)) problems.push('image order');
  if (mediaMode === 'count' && remoteFiles.length !== expected.imageCount) problems.push('image count');
  if (mediaMode === 'count' && expected.imageCount > 0) problems.push('ordered media identity requires URL checkpoint or UI verification');
  return { problems, remoteFiles };
}

function verifyPost(post, expected) {
  const { problems, remoteFiles } = postProblems(post, expected, 'urls');
  if (problems.length) throw new Error(`Post readback mismatch: ${problems.join(', ')}`);
  return remoteFiles;
}

function saveTask(taskPath, task, updates) {
  if (['published', 'updated'].includes(updates.status)) {
    updates.verification = { scope: 'vn', title: true, body: true, label: true, important: true, media_order: true, evidence: 'API getFeedId verified at ' + new Date().toISOString() };
  }
  Object.assign(task, updates);
  const temporary = `${taskPath}.tmp-${process.pid}`;
  fs.writeFileSync(temporary, `${JSON.stringify(task, null, 2)}\n`, 'utf8');
  fs.renameSync(temporary, taskPath);
}

function canonicalSource(task, source) {
  const raw = String(task.source_url || task.source_text || task.original_text || source).trim();
  const status = raw.match(/(?:x\.com|twitter\.com)\/[^/]+\/status\/(\d+)/i);
  return status ? `x-status:${status[1]}` : raw;
}

function taskFingerprint(task, expected, images, style) {
  return sha256Text(JSON.stringify({
    source: canonicalSource(task, expected.source),
    title: expected.title,
    body: expected.source,
    labelId: Number(expected.labelId),
    important: expected.important,
    imageStyle: style.name,
    imageStyleVersion: style.version,
    images: images.map((image) => ({ index: image.index, sha256: image.sha256 })),
  }));
}

function compactPost(post) {
  const files = parseRemoteFiles(post);
  return {
    id: post.id,
    language: post.language,
    title: post.title,
    label: post.newsfeedLabel?.name || null,
    important: remoteImportantValue(post.important) === '1' ? 'Yes' : 'No',
    imageCount: files.length,
    type: post.type || post.typePost || null,
    createdAt: post.createdAt || post.createTime || null,
    updatedAt: post.updatedAt || post.updateTime || null,
  };
}

function printJson(value, verbose = false) {
  process.stdout.write(`${JSON.stringify(value, null, verbose ? 2 : 0)}\n`);
}

function delay(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

function responseId(result) {
  const candidates = [result?.data?.id, result?.data?.data?.id, result?.id];
  const value = candidates.map(Number).find(Number.isInteger);
  return value || null;
}

async function findAndVerifyCreated(result, expected) {
  const id = responseId(result);
  for (const waitMs of READBACK_DELAYS_MS) {
    if (waitMs) await delay(waitMs);
    if (id) {
      try {
        const post = await getPost(id);
        verifyPost(post, expected);
        return post;
      } catch (error) {
        if (!String(error.message).includes('was not found')) throw error;
      }
    }
    const match = await findExactTitle(expected.title);
    if (match) {
      const post = await getPost(match.id);
      verifyPost(post, expected);
      return post;
    }
  }
  return null;
}

function checkpointMatches(task, files, style) {
  const checkpoint = task.api_uploads;
  if (!checkpoint || checkpoint.image_style !== style.name || checkpoint.image_style_version !== style.version) return false;
  if (!Array.isArray(checkpoint.items) || checkpoint.items.length !== files.length) return false;
  return files.every((file, offset) => {
    const item = checkpoint.items[offset];
    return item.index === file.index
      && item.source_sha256 === file.sourceSha256
      && item.rendered_sha256 === file.renderedSha256
      && typeof item.remote_url === 'string'
      && item.remote_url.startsWith('http');
  });
}

async function uploadWithCheckpoints(taskPath, task, images, outputDir) {
  const style = imageStyle(task);
  const files = await prepareUploadFiles(task, images, outputDir);
  if (checkpointMatches(task, files, style)) {
    return task.api_uploads.items.map((item) => item.remote_url);
  }
  const priorItems = task.api_uploads?.image_style === style.name
    && task.api_uploads?.image_style_version === style.version
    && Array.isArray(task.api_uploads?.items)
    ? task.api_uploads.items
    : [];
  const items = [];
  if (files.length === 0) {
    saveTask(taskPath, task, {
      status: 'upload_complete',
      publish_stage: 'uploaded',
      api_uploads: {
        image_style: style.name,
        image_style_version: style.version,
        image_count: 0,
        items: [],
      },
    });
    return [];
  }
  for (const file of files) {
    const prior = priorItems.find((item) => item.index === file.index
      && item.source_sha256 === file.sourceSha256
      && item.rendered_sha256 === file.renderedSha256
      && typeof item.remote_url === 'string'
      && item.remote_url.startsWith('http'));
    const remoteUrl = prior?.remote_url || await uploadFile(file);
    items.push({
      index: file.index,
      source_sha256: file.sourceSha256,
      rendered_sha256: file.renderedSha256,
      remote_url: remoteUrl,
    });
    saveTask(taskPath, task, {
      status: 'upload_incomplete',
      publish_stage: 'uploading',
      api_uploads: {
        image_style: style.name,
        image_style_version: style.version,
        image_count: files.length,
        items,
      },
    });
  }
  saveTask(taskPath, task, { status: 'upload_complete', publish_stage: 'uploaded' });
  return items.map((item) => item.remote_url);
}

async function matchExisting(expected, imageCount, excludeId = null, knownRemoteFiles = null) {
  const match = await findExactTitle(expected.title, excludeId);
  if (!match) return null;
  const post = await getPost(match.id);
  const compareUrls = Array.isArray(knownRemoteFiles) && knownRemoteFiles.length === imageCount;
  const comparison = postProblems(
    post,
    compareUrls ? { ...expected, remoteFiles: knownRemoteFiles } : { ...expected, imageCount },
    compareUrls ? 'urls' : 'count',
    'loose',
  );
  if (comparison.problems.length) {
    throw new Error(`Exact-title conflict with Newsfeed ${post.id}: ${comparison.problems.join(', ')}`);
  }
  return { post, remoteFiles: comparison.remoteFiles };
}

async function inspect(values) {
  if (values.id) {
    const post = await getPost(values.id);
    printJson(values.verbose ? { status: 'found', post } : { status: 'found', post: compactPost(post) }, values.verbose);
    return;
  }
  const title = required(values, 'title');
  const match = await findExactTitle(title);
  if (!match) {
    printJson({ status: 'missing', title });
    return;
  }
  const post = await getPost(match.id);
  printJson(values.verbose ? { status: 'found', post } : { status: 'found', post: compactPost(post) }, values.verbose);
}

async function render(values) {
  const { task } = loadTask(required(values, 'task'));
  const style = imageStyle(task);
  const images = await validateReadableImages(orderedImages(task, values));
  const outputDir = path.resolve(required(values, 'output-dir'));
  const files = await prepareUploadFiles(task, images, outputDir);
  printJson({
    status: 'rendered',
    imageStyle: style.name,
    imageStyleVersion: style.version,
    files: files.map((file) => ({ index: file.index, path: file.path, sha256: file.renderedSha256 })),
  }, values.verbose);
}

async function publish(values) {
  const { task, taskPath } = loadTask(required(values, 'task'));
  if (typeof task.title !== 'string' || !task.title.trim()) throw new Error('Task title is required');
  const title = task.title.trim();
  const source = bodyFromTask(task);
  const style = imageStyle(task);
  const label = await resolveLabel(task.label);
  const expected = {
    title,
    source,
    labelId: label.id,
    important: importantValue(task.important ?? 'Yes'),
    remoteFiles: [],
  };
  const knownId = task.newsfeed_id == null ? Number.NaN : Number(task.newsfeed_id);
  if (Number.isInteger(knownId)) {
    const post = await getPost(knownId);
    const hasKnownFiles = Array.isArray(task.remote_image_urls) && typeof task.task_fingerprint === 'string';
    const imageCount = Number(task.source_image_count ?? task.images?.length ?? task.remote_image_urls?.length ?? 0);
    const comparison = postProblems(
      post,
      hasKnownFiles ? { ...expected, remoteFiles: task.remote_image_urls } : { ...expected, imageCount },
      hasKnownFiles ? 'urls' : 'count',
      hasKnownFiles ? 'strict' : 'loose',
    );
    if (comparison.problems.length) {
      throw new Error(`Task Newsfeed ${knownId} no longer matches: ${comparison.problems.join(', ')}`);
    }
    printJson({ status: 'already_published', ...compactPost(post), imageStyle: style.name }, values.verbose);
    return;
  }
  const images = await validateReadableImages(orderedImages(task, values));
  const fingerprint = taskFingerprint(task, expected, images, style);
  if (task.task_fingerprint && task.task_fingerprint !== fingerprint && task.status === 'publish_uncertain') {
    throw new Error('Task content changed after an uncertain publish; resolve the prior submission before publishing again');
  }
  const checkpointUrls = Array.isArray(task.remote_image_urls)
    ? task.remote_image_urls
    : Array.isArray(task.api_uploads?.items)
      ? task.api_uploads.items.map((item) => item.remote_url)
      : null;
  const existing = await matchExisting(expected, images.length, null, checkpointUrls);
  if (existing) {
    if (values.apply) {
      saveTask(taskPath, task, {
        status: 'published',
        publish_stage: 'verified',
        newsfeed_id: existing.post.id,
        remote_image_urls: existing.remoteFiles,
        task_fingerprint: fingerprint,
      });
    }
    printJson({ status: 'already_exists', ...compactPost(existing.post), imageStyle: style.name }, values.verbose);
    return;
  }
  if (task.status === 'publish_uncertain' || ['submitted', 'submit_error'].includes(task.publish_stage)) {
    throw new Error('Previous publish is still uncertain and no matching record was found; do not resubmit automatically');
  }
  const user = currentUser();
  const plan = {
    status: 'planned',
    action: 'publish',
    language: targetCountry(task),
    title,
    label: label.name,
    labelId: label.id,
    important: expected.important,
    imageCount: images.length,
    imageStyle: style.name,
    imageStyleVersion: style.version,
    fingerprint,
    userId: user.id,
  };
  if (!values.apply) {
    printJson(plan, values.verbose);
    return;
  }
  if (task.publish_authorized !== true) throw new Error('Task does not record explicit publish authorization');
  const temporaryDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ifxdata-newsfeed-'));
  try {
    expected.remoteFiles = await uploadWithCheckpoints(taskPath, task, images, temporaryDir);
    const payload = {
      countryPost: [targetCountry(task)],
      typePost: 'sortPost',
      userId: user.id,
      important: expected.important,
      title,
      labelId: label.id,
      source,
      fileUpload: JSON.stringify(expected.remoteFiles),
      imageTicket: null,
    };
    let result;
    saveTask(taskPath, task, { status: 'publish_uncertain', publish_stage: 'submitting', task_fingerprint: fingerprint, remote_image_urls: expected.remoteFiles });
    try {
      result = await api('/feed/createPost', { method: 'POST', body: JSON.stringify(payload) });
    } catch (error) {
      saveTask(taskPath, task, {
        status: 'publish_uncertain',
        publish_stage: 'submit_error',
        task_fingerprint: fingerprint,
        remote_image_urls: expected.remoteFiles,
        publish_error: error.message,
      });
      throw new Error(`Publish response was uncertain; exact-title recovery is required before any retry: ${error.message}`);
    }
    const createdId = responseId(result);
    saveTask(taskPath, task, {
      status: 'publish_uncertain',
      publish_stage: 'submitted',
      task_fingerprint: fingerprint,
      remote_image_urls: expected.remoteFiles,
      api_response_id: createdId,
    });
    const post = await findAndVerifyCreated(result, expected);
    if (!post) throw new Error('Create returned success, but bounded readback found no verified Newsfeed; do not resubmit automatically');
    const remoteFiles = verifyPost(post, expected);
    saveTask(taskPath, task, {
      status: 'published',
      publish_stage: 'verified',
      newsfeed_id: post.id,
      remote_image_urls: remoteFiles,
      publish_error: null,
    });
    printJson({ status: 'published', id: post.id, title, language: 'Vietnam', label: label.name, imageCount: remoteFiles.length, imageStyle: style.name }, values.verbose);
  } finally {
    fs.rmSync(temporaryDir, { recursive: true, force: true });
  }
}

async function update(values) {
  const { task, taskPath } = loadTask(required(values, 'task'));
  const id = Number(values.id || task.newsfeed_id);
  if (!Number.isInteger(id)) throw new Error('--id or task.newsfeed_id is required');
  const current = await getPost(id);
  const title = typeof task.title === 'string' && task.title.trim() ? task.title.trim() : current.title;
  const source = bodyFromTask(task, current.detail);
  const duplicate = await findExactTitle(title, id);
  if (duplicate) throw new Error(`Another Newsfeed already has this exact title: ${duplicate.id}`);
  const label = task.label ? await resolveLabel(task.label) : current.newsfeedLabel;
  const important = task.important === undefined ? remoteImportantValue(current.important) : importantValue(task.important);
  if (task.replace_images !== undefined && typeof task.replace_images !== 'boolean') {
    throw new Error('Task replace_images must be true or false');
  }
  const replaceImages = task.replace_images === true;
  if (replaceImages && (!Array.isArray(task.images) || task.images.length === 0)) {
    throw new Error('replace_images is true, but the task has no replacement images');
  }
  const style = replaceImages ? imageStyle(task) : { name: 'unchanged', version: null };
  const images = replaceImages ? await validateReadableImages(orderedImages(task, values)) : [];
  const expected = {
    title,
    source,
    labelId: label.id,
    important,
    remoteFiles: replaceImages ? [] : parseRemoteFiles(current),
  };
  const fingerprint = taskFingerprint(task, expected, images, style);
  if (task.task_fingerprint && task.task_fingerprint !== fingerprint && task.status === 'update_uncertain') {
    throw new Error('Task content changed after an uncertain update; resolve the prior submission before updating again');
  }
  if (task.status === 'update_uncertain' || ['update_submitted', 'update_submit_error'].includes(task.publish_stage)) {
    const recoveryFiles = Array.isArray(task.remote_image_urls) ? task.remote_image_urls : expected.remoteFiles;
    const recovery = postProblems(current, { ...expected, remoteFiles: recoveryFiles }, 'urls');
    if (recovery.problems.length) {
      throw new Error(`Previous update remains uncertain and readback differs (${recovery.problems.join(', ')}); do not resubmit automatically`);
    }
    if (values.apply) {
      saveTask(taskPath, task, { status: 'updated', publish_stage: 'verified', newsfeed_id: id, remote_image_urls: recovery.remoteFiles, update_error: null });
    }
    printJson({ status: 'updated_recovered', ...compactPost(current), imageStyle: style.name }, values.verbose);
    return;
  }
  const plan = {
    status: 'planned',
    action: 'update',
    id,
    title,
    label: label?.name,
    important,
    replaceImages,
    imageCount: replaceImages ? images.length : expected.remoteFiles.length,
    imageStyle: style.name,
    imageStyleVersion: style.version,
    fingerprint,
  };
  if (!values.apply) {
    printJson(plan, values.verbose);
    return;
  }
  if (task.edit_authorized !== true) throw new Error('Task does not record explicit edit authorization');
  let remoteFiles = expected.remoteFiles;
  let temporaryDir = null;
  try {
    if (replaceImages) {
      temporaryDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ifxdata-newsfeed-'));
      remoteFiles = await uploadWithCheckpoints(taskPath, task, images, temporaryDir);
    }
    const payload = {
      id,
      pathName: 'vn',
      type: 'NF',
      title,
      important,
      labelId: label.id,
      source,
      fileUpload: JSON.stringify(remoteFiles),
    };
    saveTask(taskPath, task, { status: 'update_uncertain', publish_stage: 'update_submitting', task_fingerprint: fingerprint, remote_image_urls: remoteFiles });
    try {
      await api('/feed/updatePost', { method: 'POST', body: JSON.stringify(payload) });
    } catch (error) {
      saveTask(taskPath, task, {
        status: 'update_uncertain',
        publish_stage: 'update_submit_error',
        task_fingerprint: fingerprint,
        remote_image_urls: remoteFiles,
        update_error: error.message,
      });
      throw new Error(`Update response was uncertain; readback recovery is required before any retry: ${error.message}`);
    }
    saveTask(taskPath, task, {
      status: 'update_uncertain',
      publish_stage: 'update_submitted',
      task_fingerprint: fingerprint,
      remote_image_urls: remoteFiles,
    });
    const post = await getPost(id);
    verifyPost(post, { title, source, important, labelId: label.id, remoteFiles });
    saveTask(taskPath, task, { status: 'updated', publish_stage: 'verified', newsfeed_id: id, remote_image_urls: remoteFiles, update_error: null });
    printJson({ status: 'updated', id, title, language: 'Vietnam', label: label.name, imageCount: remoteFiles.length, imageStyle: style.name }, values.verbose);
  } finally {
    if (temporaryDir) fs.rmSync(temporaryDir, { recursive: true, force: true });
  }
}

function assertApplyAllowed(taskPath) {
  const task = taskPath && fs.existsSync(taskPath) ? loadTask(taskPath).task : {};
  const override = task.explicit_publish_override === true && task.publish_authorized === true && typeof task.authorization_evidence === 'string' && task.authorization_evidence.trim();
  const operations = JSON.parse(fs.readFileSync(OPERATIONS_FILE, 'utf8')).operations;
  if (!override && (operations?.mode !== 'publish' || operations?.publish_authorized !== true)) throw new Error('chat_preview mode: backend uploads/create/update are disabled');
}

async function main() {
  const { command, values } = parseArgs(process.argv.slice(2));
  if (values.apply) assertApplyAllowed(values.task);
  if (command === 'inspect') return inspect(values);
  if (command === 'render') return render(values);
  if (command === 'publish') return publish(values);
  if (command === 'update') return update(values);
  throw new Error('Command must be one of: inspect, render, publish, update');
}

main().catch((error) => {
  const verbose = process.argv.includes('--verbose');
  process.stderr.write(`${verbose ? (error.stack || error) : error.message || error}\n`);
  process.exitCode = 1;
});
