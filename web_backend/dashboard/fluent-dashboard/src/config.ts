// src/config.ts

// Licensed under the Fluent Signal Copier Limited Use License v1.0
// See LICENSE.txt for terms. No warranty; use at your own risk.
// Copyright (c) 2025 R4V3N. All rights reserved.


// Prefer env overrides; otherwise, assume API on same host.
// If you're on Vite dev (5173), map to backend 8000 automatically.
const HOST = window.location.host;
const sameHostApi =
    window.location.protocol + '//' +
    (HOST.includes(':5173') ? HOST.replace(':5173', ':8000') : HOST);

export const API_BASE =
    (import.meta as any).env?.VITE_API_BASE ?? `${sameHostApi}`;
