/*
 * Runner ELK para c4norm.
 * Lee grafos ELK (JSON), uno por línea de stdin, y por cada uno escribe una
 * línea de salida por stdout con el resultado del layout (o {"error": ...}
 * si ese grafo puntual falla). No sale del proceso ante un error de layout:
 * así el mismo proceso Node se reutiliza entre diagramas (evita pagar el
 * arranque de Node, ~100-400 ms, en cada normalización).
 */
"use strict";

const readline = require("readline");
const ELK = require("elkjs");
const elk = new ELK();

const rl = readline.createInterface({ input: process.stdin, terminal: false });

// stdin puede cerrarse (fin de un one-shot) mientras un layout async sigue en
// vuelo; no salir hasta que el último `line` pendiente termine de responder.
let pending = 0;
let closing = false;

rl.on("line", async (line) => {
  if (!line.trim()) return;
  pending++;
  let response;
  try {
    const graph = JSON.parse(line.replace(/^﻿/, ""));
    response = await elk.layout(graph);
  } catch (err) {
    response = { error: String((err && err.stack) || err) };
  }
  process.stdout.write(JSON.stringify(response) + "\n");
  pending--;
  if (closing && pending === 0) process.exit(0);
});

rl.on("close", () => {
  closing = true;
  if (pending === 0) process.exit(0);
});
