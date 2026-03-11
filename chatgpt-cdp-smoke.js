#!/usr/bin/env node
"use strict";

const fs = require("fs");
const path = require("path");

function loadPlaywright() {
  try {
    return require("playwright");
  } catch (_error) {
    const localAppData = process.env.LOCALAPPDATA;
    if (!localAppData) {
      throw _error;
    }
    const runnerPath = path.join(localAppData, "CodexChatGPTRunner", "node_modules", "playwright");
    return require(runnerPath);
  }
}

async function main() {
  const [, , configPath] = process.argv;
  if (!configPath) {
    throw new Error("Usage: node chatgpt-cdp-smoke.js <config.json>");
  }

  const config = JSON.parse(fs.readFileSync(configPath, "utf8"));
  const {
    debugUrl,
    payloadPath,
    outputPath,
    attachmentPaths = [],
    beginMarker,
    endMarker,
    timeoutMs = 120000,
    connectTimeoutMs = 120000,
    projectUrl = "",
    modelLabel = "",
    modelStrategy = "ignore",
    preferNewPage = false,
    prepareOnly = false,
    inspectExistingReviewsOnly = false,
  } = config;

  if (!debugUrl) {
    throw new Error("Missing required config fields.");
  }
  if (!prepareOnly && !inspectExistingReviewsOnly && (!payloadPath || !outputPath || !beginMarker || !endMarker)) {
    throw new Error("Missing required config fields.");
  }

  const payload = prepareOnly || inspectExistingReviewsOnly ? "" : fs.readFileSync(payloadPath, "utf8");
  const playwright = loadPlaywright();
  const browser = await playwright.chromium.connectOverCDP(debugUrl, { timeout: connectTimeoutMs });

  function normalizeModelLabel(value) {
    return String(value || "")
      .toLowerCase()
      .replace(/chatgpt/g, "")
      .replace(/\s+/g, " ")
      .trim();
  }

  function modelTestIdForLabel(value) {
    const normalized = normalizeModelLabel(value);
    const entries = [
      [["5.3 instant", "instant 5.3", "gpt 5.3 instant"], "model-switcher-gpt-5-3-instant"],
      [["5.4 thinking", "thinking 5.4", "gpt 5.4 thinking"], "model-switcher-gpt-5-4-thinking"],
      [["5.4 pro", "pro 5.4", "gpt 5.4 pro"], "model-switcher-gpt-5-4-pro"],
    ];
    for (const [aliases, testId] of entries) {
      if (aliases.includes(normalized)) {
        return testId;
      }
    }
    return "";
  }

  async function readCurrentModelText(page) {
    const button = page.getByTestId("model-switcher-dropdown-button").first();
    await button.waitFor({ timeout: 20000 });
    const [text, aria] = await Promise.all([
      button.innerText().catch(() => ""),
      button.getAttribute("aria-label").catch(() => ""),
    ]);
    return `${text || ""} ${aria || ""}`.trim();
  }

  async function ensureModelSelection(page, desiredLabel, strategy) {
    if (!desiredLabel || strategy === "ignore") {
      return;
    }

    const currentText = await readCurrentModelText(page);
    const normalizedCurrent = normalizeModelLabel(currentText);
    const normalizedDesired = normalizeModelLabel(desiredLabel);
    if (normalizedCurrent.includes(normalizedDesired)) {
      return;
    }

    if (strategy === "current") {
      throw new Error(`Current ChatGPT model mismatch. Wanted "${desiredLabel}", but saw "${currentText}".`);
    }

    if (strategy !== "select") {
      throw new Error(`Unsupported model strategy: ${strategy}`);
    }

    const modelTestId = modelTestIdForLabel(desiredLabel);
    if (!modelTestId) {
      throw new Error(`Unsupported ChatGPT model label for automation: ${desiredLabel}`);
    }

    const button = page.getByTestId("model-switcher-dropdown-button").first();
    await button.click();
    const menuItem = page.getByTestId(modelTestId).first();
    await menuItem.waitFor({ timeout: 10000 });
    await menuItem.click();

    const deadline = Date.now() + 15000;
    while (Date.now() < deadline) {
      const afterText = await readCurrentModelText(page);
      if (normalizeModelLabel(afterText).includes(normalizedDesired)) {
        return;
      }
      await page.waitForTimeout(500);
    }

    const afterText = await readCurrentModelText(page);
    throw new Error(`Failed to switch ChatGPT model to "${desiredLabel}". Current button text: "${afterText}".`);
  }

  async function clearEditor(page, editor) {
    await editor.click();
    await page.keyboard.press("Control+A").catch(() => {});
    await page.keyboard.press("Backspace").catch(() => {});
    await editor.evaluate((node) => {
      node.textContent = "";
      node.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "deleteContentBackward", data: null }));
    }).catch(() => {});
  }

  function normalizePromptText(value) {
    return String(value || "")
      .replace(/\r\n?/g, "\n")
      .replace(/\u00a0/g, " ")
      .replace(/\u200b/g, "")
      .trim();
  }

  async function readEditorText(editor) {
    const [innerText, textContent] = await Promise.all([
      editor.innerText().catch(() => ""),
      editor.evaluate((node) => node.textContent || "").catch(() => ""),
    ]);
    return { innerText, textContent };
  }

  function isPromptEquivalent(expected, actual) {
    return normalizePromptText(expected) === normalizePromptText(actual);
  }

  async function attachmentNamesPresent(page, names) {
    return await page.evaluate((expectedNames) => {
      const composerRoot = document.querySelector("form") || document.body;
      if (!(composerRoot instanceof HTMLElement)) {
        return false;
      }
      const text = composerRoot.innerText || "";
      return expectedNames.every((name) => text.includes(name));
    }, names).catch(() => false);
  }

  function isImageOnlyInput(acceptValue) {
    const value = String(acceptValue || "").trim().toLowerCase();
    return !!value && value.split(",").every((entry) => entry.trim().startsWith("image/"));
  }

  async function waitForAttachmentNames(page, names, timeoutMs = 30000) {
    const started = Date.now();
    while (Date.now() - started < timeoutMs) {
      if (await attachmentNamesPresent(page, names)) {
        return true;
      }
      await page.waitForTimeout(500);
    }
    return false;
  }

  async function clickAttachmentButton(page) {
    const candidates = [
      page.getByTestId("composer-plus-btn").first(),
      page.locator('button[aria-label*="파일"]').first(),
      page.locator('button[aria-label*="Add files"]').first(),
      page.locator('button[aria-label*="첨부"]').first(),
    ];
    for (const candidate of candidates) {
      try {
        await candidate.waitFor({ timeout: 1000 });
        await candidate.click();
        await page.waitForTimeout(500);
        return true;
      } catch (_error) {
        continue;
      }
    }
    return false;
  }

  async function uploadAttachments(page, filePaths) {
    if (!Array.isArray(filePaths) || !filePaths.length) {
      return;
    }
    const resolvedPaths = filePaths.map((filePath) => path.resolve(String(filePath)));
    for (const filePath of resolvedPaths) {
      fs.accessSync(filePath, fs.constants.R_OK);
    }
    const names = resolvedPaths.map((filePath) => path.basename(filePath));
    const attempts = [
      async () => {},
      async () => {
        await clickAttachmentButton(page);
      },
    ];
    let lastError = "";
    for (const prepare of attempts) {
      await prepare();
      const inputs = page.locator('input[type="file"]');
      const inputCount = await inputs.count().catch(() => 0);
      for (let index = 0; index < inputCount; index += 1) {
        const input = inputs.nth(index);
        const accept = await input.getAttribute("accept").catch(() => "");
        if (isImageOnlyInput(accept)) {
          continue;
        }
        try {
          await input.setInputFiles(resolvedPaths);
          if (await waitForAttachmentNames(page, names)) {
            return;
          }
          lastError = `Attachment upload did not surface file names in the composer: ${names.join(", ")}`;
        } catch (error) {
          lastError = `Attachment upload failed via input ${index}: ${String((error && error.message) || error)}`;
        }
      }
    }
    throw new Error(lastError || `Could not find a usable ChatGPT file input for: ${names.join(", ")}`);
  }

  function normalizeProjectScope(projectUrl) {
    const value = String(projectUrl || "").replace(/\/+$/, "");
    if (!value) {
      return "";
    }
    if (value.endsWith("/project")) {
      return value.slice(0, -"/project".length);
    }
    return value;
  }

  function pageMatchesProjectScope(pageUrl, projectUrl) {
    const url = String(pageUrl || "");
    if (!url.startsWith("https://chatgpt.com/")) {
      return false;
    }
    const scope = normalizeProjectScope(projectUrl);
    if (!scope) {
      return true;
    }
    return url.startsWith(scope);
  }

  function isResponseGenerating(text) {
    const body = String(text || "");
    return [
      "ChatGPT가 아직 응답을 생성 중입니다",
      "ChatGPT is still generating a response",
      "Pro 생각 중",
      "Pro thinking",
      "Thought for",
      "스트리밍이 중지되었습니다. 메시지 완료를 기다리는 중입니다",
    ].some((pattern) => body.includes(pattern));
  }

  function extractCompletedReview(text, beginMarker, endMarker) {
    const body = String(text || "");
    const promptBeginIndex = body.indexOf(beginMarker);
    if (promptBeginIndex < 0) {
      return null;
    }
    const answerBeginIndex = body.indexOf(beginMarker, promptBeginIndex + beginMarker.length);
    if (answerBeginIndex < 0) {
      return null;
    }
    const answerEndIndex = body.indexOf(endMarker, answerBeginIndex + beginMarker.length);
    if (answerEndIndex < 0 || answerEndIndex <= answerBeginIndex) {
      return null;
    }
    return body.slice(answerBeginIndex + beginMarker.length, answerEndIndex).trim();
  }

  function analyzeReviewMarkers(text, beginMarker, endMarker) {
    const body = String(text || "");
    const beginCount = beginMarker ? body.split(beginMarker).length - 1 : 0;
    const endCount = endMarker ? body.split(endMarker).length - 1 : 0;
    const review = beginMarker && endMarker ? extractCompletedReview(body, beginMarker, endMarker) : null;
    return {
      beginCount,
      endCount,
      review,
      isGenerating: isResponseGenerating(body),
    };
  }

  function analyzeExistingReviewPage(text) {
    const body = String(text || "");
    const markerCounts = new Map();
    for (const match of body.matchAll(/\b(?:BEGIN|END)_CDX_REVIEW_[A-Za-z0-9_]+\b/g)) {
      const marker = String(match[0] || "");
      markerCounts.set(marker, (markerCounts.get(marker) || 0) + 1);
    }
    let beginCount = 0;
    let endCount = 0;
    let hasCompleteMarkers = false;
    for (const [marker, count] of markerCounts.entries()) {
      if (marker.startsWith("BEGIN_CDX_REVIEW_")) {
        beginCount += count;
        const endMarker = marker.replace("BEGIN_CDX_REVIEW_", "END_CDX_REVIEW_");
        if (count >= 2 && (markerCounts.get(endMarker) || 0) >= 2) {
          hasCompleteMarkers = true;
        }
      } else if (marker.startsWith("END_CDX_REVIEW_")) {
        endCount += count;
      }
    }
    const hasMarkers = beginCount > 0 || endCount > 0;
    const isGenerating = isResponseGenerating(body);
    let state = "none";
    if (hasMarkers) {
      if (hasCompleteMarkers) {
        state = "complete";
      } else if (isGenerating) {
        state = "pending";
      } else {
        state = "incomplete";
      }
    }
    return {
      beginCount,
      endCount,
      hasMarkers,
      hasCompleteMarkers,
      isGenerating,
      state,
    };
  }

  async function injectPromptViaDom(editor, payloadText) {
    await editor.evaluate((node, text) => {
      node.textContent = text;
      node.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: text }));
      node.dispatchEvent(new Event("change", { bubbles: true }));
    }, payloadText);
  }

  async function injectPromptViaInsertText(page, payloadText) {
    const chunks = [];
    const chunkSize = 4000;
    for (let index = 0; index < payloadText.length; index += chunkSize) {
      chunks.push(payloadText.slice(index, index + chunkSize));
    }
    for (const chunk of chunks) {
      await page.keyboard.insertText(chunk);
      await page.waitForTimeout(20);
    }
  }

  async function injectPromptViaClipboard(page, editor, payloadText) {
    await page.evaluate(async (text) => {
      await navigator.clipboard.writeText(text);
    }, payloadText);
    await editor.click();
    await page.keyboard.press("Control+V");
    await page.waitForTimeout(1000);
  }

  async function injectPrompt(page, editor, payloadText) {
    await clearEditor(page, editor);
    const strategies = [
      ["dom-set", async () => injectPromptViaDom(editor, payloadText)],
      ["clipboard", async () => injectPromptViaClipboard(page, editor, payloadText)],
      ["insert-text", async () => injectPromptViaInsertText(page, payloadText)],
    ];
    let lastError = "";
    for (const [label, action] of strategies) {
      await clearEditor(page, editor);
      try {
        await action();
        const { innerText, textContent } = await readEditorText(editor);
        if (isPromptEquivalent(payloadText, textContent) || isPromptEquivalent(payloadText, innerText)) {
          return;
        }
        lastError = `Prompt injection mismatch after ${label}. Expected ${payloadText.length} chars, saw innerText=${innerText.length}, textContent=${textContent.length}.`;
      } catch (error) {
        lastError = `Prompt injection failed via ${label}: ${String((error && error.message) || error)}`;
      }
    }
    throw new Error(lastError || `Prompt injection appears incomplete. Expected ${payloadText.length} chars.`);
  }

  async function submitPrompt(page, editor) {
    await page.keyboard.press("Enter").catch(() => {});
    await page.waitForTimeout(1200);

    const residualText = await editor.innerText().catch(() => "");
    if (!residualText.trim()) {
      return;
    }

    const candidates = [
      page.getByTestId("send-button").first(),
      page.locator('button[aria-label*="Send"]').first(),
      page.locator('button[aria-label*="전송"]').first(),
      page.locator('button[aria-label*="Submit"]').first(),
      page.locator('button svg').locator("..").first(),
    ];

    for (const candidate of candidates) {
      try {
        await candidate.waitFor({ timeout: 1500 });
        await candidate.click();
        await page.waitForTimeout(1200);
        const afterText = await editor.innerText().catch(() => "");
        if (!afterText.trim()) {
          return;
        }
      } catch (_error) {
        continue;
      }
    }

    const nearestButton = await page.evaluate(() => {
      const editorNode = document.querySelector("#prompt-textarea");
      if (!(editorNode instanceof HTMLElement)) {
        return null;
      }
      const editorRect = editorNode.getBoundingClientRect();
      const buttons = Array.from(document.querySelectorAll("button")).filter((button) => {
        if (!(button instanceof HTMLButtonElement) || button.disabled) {
          return false;
        }
        const style = window.getComputedStyle(button);
        if (style.visibility === "hidden" || style.display === "none") {
          return false;
        }
        const rect = button.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0;
      });
      let bestButton = null;
      let bestScore = Number.POSITIVE_INFINITY;
      for (const button of buttons) {
        const rect = button.getBoundingClientRect();
        const centerX = rect.left + rect.width / 2;
        const centerY = rect.top + rect.height / 2;
        const targetX = editorRect.right;
        const targetY = editorRect.bottom;
        const distance = (centerX - targetX) ** 2 + (centerY - targetY) ** 2;
        if (distance < bestScore) {
          bestScore = distance;
          bestButton = button;
        }
      }
      if (!bestButton) {
        return null;
      }
      bestButton.click();
      return {
        aria: bestButton.getAttribute("aria-label") || "",
        text: (bestButton.innerText || "").trim(),
        testid: bestButton.getAttribute("data-testid") || "",
      };
    }).catch(() => null);
    if (nearestButton) {
      await page.waitForTimeout(1200);
      const afterNearestClickText = await editor.innerText().catch(() => "");
      if (!afterNearestClickText.trim()) {
        return;
      }
    }

    throw new Error("Prompt submit did not clear the editor after Enter and send-button fallbacks.");
  }

  try {
    const context = browser.contexts()[0];
    if (!context) {
      throw new Error("No browser context found.");
    }

    const pages = context.pages();
    const pageSummaries = pages.map((page, index) => ({
      index,
      url: page.url(),
      title: page.isClosed() ? "(closed)" : undefined,
    }));

    if (inspectExistingReviewsOnly) {
      const reviewPages = [];
      for (const candidate of pages) {
        const url = candidate.url() || "";
        if (!pageMatchesProjectScope(url, projectUrl)) {
          continue;
        }
        const text = await candidate.locator("body").innerText().catch(() => "");
        const markerState = analyzeExistingReviewPage(text);
        if (!markerState.hasMarkers) {
          continue;
        }
        reviewPages.push({
          url,
          state: markerState.state,
          beginCount: markerState.beginCount,
          endCount: markerState.endCount,
          isGenerating: markerState.isGenerating,
        });
      }
      console.log(
        JSON.stringify({
          ok: true,
          inspected: true,
          projectUrl,
          pages: pageSummaries,
          reviewPages,
          pendingReviews: reviewPages.filter((entry) => entry.state !== "complete"),
        }),
      );
      return;
    }

    let page = null;
    let sourcePage = null;
    if (projectUrl) {
      sourcePage = pages.find((candidate) => (candidate.url() || "").startsWith(projectUrl));
    }
    if (!sourcePage) {
      sourcePage = pages.find((candidate) => {
        const url = candidate.url() || "";
        return url.startsWith("https://chatgpt.com/") && !url.includes("auth/login");
      });
    }
    if (!sourcePage) {
      sourcePage = pages[0] || null;
    }

    if (preferNewPage) {
      page = await context.newPage();
    } else {
      page = sourcePage || (await context.newPage());
    }

    await page.bringToFront();
    const targetUrl = projectUrl || (preferNewPage && sourcePage ? sourcePage.url() : "");
    if (targetUrl && ((preferNewPage && (page.url() || "") !== targetUrl) || (projectUrl && !(page.url() || "").startsWith(projectUrl)))) {
      await page.goto(targetUrl, { waitUntil: "domcontentloaded", timeout: 120000 }).catch(() => {});
    }

    await page.waitForTimeout(1000);
    await ensureModelSelection(page, modelLabel, modelStrategy);

    const url = page.url();
    const body = await page.locator("body").innerText().catch(() => "");
    const lower = `${url}\n${body}`.toLowerCase();

    if (lower.includes("verify you are human") || lower.includes("just a moment") || lower.includes("cloudflare")) {
      throw new Error(`Human verification is blocking the current page: ${url}`);
    }
    if (lower.includes("log in") || lower.includes("sign up for free")) {
      throw new Error(`Login is required for the current page: ${url}`);
    }

    if (prepareOnly) {
      console.log(
        JSON.stringify({
          ok: true,
          prepared: true,
          url: page.url(),
          pages: pageSummaries,
          modelLabel,
          modelStrategy,
        }),
      );
      return;
    }

    const editor = page.locator("#prompt-textarea").first();
    await editor.waitFor({ timeout: 20000 });
    await uploadAttachments(page, attachmentPaths);
    await injectPrompt(page, editor, payload);
    await submitPrompt(page, editor);

    const started = Date.now();
    let lastMarkerState = {
      beginCount: 0,
      endCount: 0,
      review: null,
      isGenerating: false,
    };
    while (Date.now() - started < timeoutMs) {
      const text = await page.locator("body").innerText().catch(() => "");
      lastMarkerState = analyzeReviewMarkers(text, beginMarker, endMarker);
      if (lastMarkerState.review !== null) {
        fs.writeFileSync(outputPath, lastMarkerState.review, "utf8");
        console.log(
          JSON.stringify({
            ok: true,
            url: page.url(),
            pages: pageSummaries,
            outputPath,
            reviewLength: lastMarkerState.review.length,
            reviewPreview: lastMarkerState.review.slice(0, 200),
          }),
        );
        return;
      }
      await page.waitForTimeout(2000);
    }

    if (lastMarkerState.isGenerating) {
      throw new Error(`Review is still generating without completion markers on ${page.url()}`);
    }
    if (lastMarkerState.beginCount > 0 || lastMarkerState.endCount > 0) {
      throw new Error(
        `Review finished without a complete marker pair on ${page.url()} (beginCount=${lastMarkerState.beginCount}, endCount=${lastMarkerState.endCount})`,
      );
    }
    throw new Error(`Timed out waiting for markers on ${page.url()}`);
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(String((error && error.stack) || error));
  process.exit(1);
});
