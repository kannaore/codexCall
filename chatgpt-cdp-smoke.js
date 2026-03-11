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
    beginMarker,
    endMarker,
    timeoutMs = 120000,
    connectTimeoutMs = 120000,
    projectUrl = "",
    modelLabel = "",
    modelStrategy = "ignore",
    preferNewPage = false,
    prepareOnly = false,
  } = config;

  if (!debugUrl) {
    throw new Error("Missing required config fields.");
  }
  if (!prepareOnly && (!payloadPath || !outputPath || !beginMarker || !endMarker)) {
    throw new Error("Missing required config fields.");
  }

  const payload = prepareOnly ? "" : fs.readFileSync(payloadPath, "utf8");
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

  async function injectPrompt(page, editor, payloadText) {
    await clearEditor(page, editor);
    const chunks = [];
    const chunkSize = 4000;
    for (let index = 0; index < payloadText.length; index += chunkSize) {
      chunks.push(payloadText.slice(index, index + chunkSize));
    }
    for (const chunk of chunks) {
      await page.keyboard.insertText(chunk);
      await page.waitForTimeout(20);
    }
    const editorText = await editor.innerText().catch(() => "");
    if (!editorText || editorText.length < Math.min(payloadText.length, 200)) {
      throw new Error(`Prompt injection appears incomplete. Expected ${payloadText.length} chars, saw ${editorText.length}.`);
    }
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
    await injectPrompt(page, editor, payload);
    await submitPrompt(page, editor);

    const started = Date.now();
    while (Date.now() - started < timeoutMs) {
      const text = await page.locator("body").innerText().catch(() => "");
      const beginCount = text.split(beginMarker).length - 1;
      const endCount = text.split(endMarker).length - 1;
      const beginIndex = text.lastIndexOf(beginMarker);
      const endIndex = text.lastIndexOf(endMarker);
      if (beginCount >= 2 && endCount >= 2 && beginIndex >= 0 && endIndex > beginIndex) {
        const review = text.slice(beginIndex + beginMarker.length, endIndex).trim();
        fs.writeFileSync(outputPath, review, "utf8");
        console.log(
          JSON.stringify({
            ok: true,
            url: page.url(),
            pages: pageSummaries,
            outputPath,
            reviewLength: review.length,
            reviewPreview: review.slice(0, 200),
          }),
        );
        return;
      }
      await page.waitForTimeout(2000);
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
