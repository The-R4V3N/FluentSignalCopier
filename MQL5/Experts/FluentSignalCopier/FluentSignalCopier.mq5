//+------------------------------------------------------------------+
//|                                         Fluent Signal Copier.mq5 |
//|                              https://www.mql5.com/en/users/r4v3n |
//| Licensed under the Fluent Signal Copier Limited Use License v1.0 |
//| See LICENSE.txt for terms. No warranty; use at your own risk.    |
//| Copyright (c) 2025 R4V3N. All rights reserved.                   |
//+------------------------------------------------------------------+
#property copyright "Copyright 2025, R4V3N"
#property link "https://www.mql5.com/en/users/r4v3n"
#property version "1.00"
#property strict

#include <Trade/Trade.mqh>
#include <Trade/SymbolInfo.mqh>
#include <Trade/AccountInfo.mqh>
#include <Trade/PositionInfo.mqh>

CTrade g_trade;
CSymbolInfo g_sym;
CAccountInfo g_acc;
CPositionInfo g_positionInfo;

//--- File Configuration Group
input group "====== FILE CONFIGURATION ======" input bool InpDebug = false; // Print debug info to Experts tab
input string InpSignalFileName = "Fluent_signals.jsonl";                    // In MQL5/Files/
input string InpHeartbeatFileName = "Fluent_heartbeat.txt";                 // In MQL5/Files/
input string InpPositionsFileName = "Fluent_positions.json";                // In MQL5/Files/

//--- Break-Even Configuration Group
input group "====== BRAKE EVEN ======" input bool InpBE_Enable = true; // Enable SL -> BE auto-move on trigger
input int InpBE_TriggerTP = 1;                                         // 0=Off; 1..N: which TP triggers BE (default TP1)
input bool InpBE_AutoOnTP1 = true;                                     // Auto-arm BE when TP1 arrives via MODIFY
input bool InpBE_Logging = true;                                       // Verbose BE logs to Experts tab
input int InpBE_CleanupEveryMin = 60;                                  // Run BE cleanup every N minutes
input int InpBE_OffsetPoints = 0;                                      // Optional offset from exact BE (points), can be negative

//--- Symbol Configuration Group
input group "====== SYMBOL CONFIGURATION ======" input string InpSymbolPrefix = ""; // Broker always appends “+” to everything
input string InpSymbolSuffix = "";                                                  // Only some symbols have “+” (others are plain)
input string InpSymbolSuffixVariants = "";                                          // Your default suffix is something else (e.g. “.a”), but some symbols show up with “+” instead
// Order matters; tried after Prefix+Suffix

//--- Trading Parameters Group
input group "====== TRADING PARAMETES ======" input double InpDefaultLots = 0.01; // Used if no lots/risk
input double InpRiskPercent = 1.0;                                                // Used if SL provided and no risk in JSON
input ulong InpMagic = 20250810;                                                  // Magic number for all orders
input int InpSlippagePoints = 50;                                                 // Slippage in points (0 = no slippage)
input bool InpAllowBuys = true;                                                   // Allow BUY orders
input bool InpAllowSells = true;                                                  // Allow SELL orders
input bool InpCloseConflicts = false;                                             // Close opposite positions before new

//--- Heartbeat Configuration Group
input group "====== HEARTBEAT CONFIGURATION ======" input bool InpEnableHeartbeat = true; // Monitor GUI heartbeat
input int HeartbeatSeconds = 5;                                                           // Writes the Heartbeat every # Second
input int InpHeartbeatTimeout = 60;                                                       // Seconds before stale warning
input bool InpSnapshotOnlyMagic = false;                                                  // Snapshot: only include this EA's magic?

//--- Multi-Position Management Group
input group "====== MULTI-POSITION MANAGEMENT ======" input int InpMaxPositions = 5; // Maximum positions per signal (1-10)
input bool InpSkipBadTPs = true;                                                     // Drop TPs on wrong side of entry
input int InpPositionsToOpen = 0;                                                    // 0 = auto (use TP count, capped by Max); >0 = force this many legs
input bool InpRiskPerLeg = false;                                                    // false=Per-Signal (current behavior), true=Per-Leg (risk scales with leg count)
input bool InpUseCustomLots = false;                                                 // Use custom lot sizes per TP (ignores risk calc)
input double InpTP1_Lots = 0.02;                                                     // TP1: Lot size (if custom lots enabled)
input double InpTP2_Lots = 0.01;                                                     // TP2: Lot size (if custom lots enabled)
input double InpTP3_Lots = 0.01;                                                     // TP3: Lot size (if custom lots enabled)
input double InpTP4_Lots = 0.01;                                                     // TP4: Lot size (if custom lots enabled)
input double InpTP5_Lots = 0.01;                                                     // TP5+: Lot size (if custom lots enabled)

//--- Safety Caps Group
input group "====== SEAFTY CAPS ======" input double InpMaxLotOverall = 0.05; // Absolute ceiling for any order
input double InpMaxLot_Metal = 0.05;                                          // Metals (XAU/XAG) cap
input double InpMaxLot_Oil = 0.05;                                            // e.g., XTIUSD / XBRUSD
input double InpMaxLot_Index = 0.05;                                          // e.g., US30, NAS100, DE40...
input double InpMaxLot_FX = 0.05;                                             // Major/minor FX pairs
input double InpMaxLot_Crypto = 0.05;                                         // BTCUSD, ETHUSD etc.
input double InpRiskDollarCap = 15.0;                                         // Hard cap on $ at risk per trade (0 = disable)

//--- System Features Group
input group "====== SYSTEM FEATURES ======" input bool InpWriteSnapshots = true; // Write position snapshots for GUI
input bool InpSoundAlerts = true;                                                // Play sound on important events
input bool InpSourceTags = true;                                                 // Add 6-char source tags to comments

//--- Alert Configuration Group
input group "====== ALERT CONFIGURATION ======" input bool InpAlertOnOpen = true; // Play alert on OPEN
input bool InpAlertOnClose = true;                                                // Play alert on CLOSE
input bool InpAlertOnEmergency = true;                                            // Play alert on EMERGENCY close
input bool InpAlertOnModify = false;                                              // Play alert on MODIFY (default off)

//--- Heartbeat Warning Control Group
input group "====== HEARTBEAT WARNING CONTROL ======" input bool InpHeartbeatPopupAlerts = false; // Show MT5 Alert() popups for stale heartbeat
input bool InpHeartbeatPrintWarnings = true;                                                      // Always Print() stale warnings to Experts tab
input int InpHeartbeatWarnInterval = 300;                                                         // Seconds between repeated stale warnings

//--- Time Management
input group "====== TIME MANAGEMENT ======" input bool InpTimeFilter = true; // Enable time/day filter for NEW OPENS
input string InpStartTimeHHMM = "01:00";                                     // Start time (broker/server time)
input string InpEndTimeHHMM = "23:59";                                       // End time   (broker/server time)
input bool InpTradeMonday = true;                                            // Trade on Monday ?
input bool InpTradeTuesday = true;                                           // Trade on Tuesday ?
input bool InpTradeWednesday = true;                                         // Trade on Wednesday ?
input bool InpTradeThursday = true;                                          // Trade on Thursday ?
input bool InpTradeFriday = true;                                            // Trade on Friday ?
input bool InpTradeSaturday = false;                                         // Trade on Saturday ?
input bool InpTradeSunday = false;                                           // Trade on Sunday ?

//----- Global Variables -----
datetime g_last_heartbeat = 0;
int g_lastBeat = 0;
datetime g_last_snapshot = 0;
bool g_emergency_mode = false;
int g_positions_closed_emergency = 0;

string g_signal_file = InpSignalFileName;       // Fluent_signals.jsonl
string g_heartbeat_file = InpHeartbeatFileName; // Fluent_heartbeat.txt
string g_snapshot_file = InpPositionsFileName;  // Fluent_positions.json

// --- Fallback map: OID -> source + tag (for robust CLOSE attribution)
ulong g_oid_keys[];
string g_oid_sources[];
string g_oid_tags[];

// ---------- Small helpers ----------
double NaN() { return MathSqrt(-1.0); }
string Trim(const string s)
{
   string t = s;
   StringTrimLeft(t);
   StringTrimRight(t);
   return t;
}

// Generate 6-char hex tag from source string (simple hash)
string GenerateSourceTag(const string source)
{
   if (!InpSourceTags)
      return "";

   ulong hash = 5381;
   for (int i = 0; i < StringLen(source); i++)
   {
      hash = ((hash << 5) + hash) + StringGetCharacter(source, i);
   }

   string hex = "";
   string chars = "0123456789ABCDEF";
   for (int i = 0; i < 6; i++)
   {
      hex += StringSubstr(chars, (int)(hash % 16), 1);
      hash /= 16;
   }
   return hex;
}

// UTF-8 line reader (FILE_BIN)
bool ReadLineUtf8(const int handle, string &out)
{
   out = "";
   if (handle == INVALID_HANDLE || FileIsEnding(handle))
      return false;

   uchar buf[];
   ArrayResize(buf, 0);

   while (!FileIsEnding(handle))
   {
      uchar c_arr[1];
      uint bytes_read = FileReadArray(handle, c_arr, 0, 1);
      if (bytes_read == 0)
         break;

      int c = (int)c_arr[0];
      if (c == 10)
         break; // '\n'

      if (c == 13) // '\r' — also eat optional '\n'
      {
         if (!FileIsEnding(handle))
         {
            ulong pos = FileTell(handle);
            uchar next_arr[1];
            uint next_read = FileReadArray(handle, next_arr, 0, 1);
            if (next_read > 0 && next_arr[0] != 10)
               FileSeek(handle, pos, SEEK_SET);
         }
         break;
      }

      int n = ArraySize(buf);
      ArrayResize(buf, n + 1);
      buf[n] = (uchar)c;
   }

   out = CharArrayToString(buf, 0, ArraySize(buf), CP_UTF8);
   return (StringLen(out) > 0 || !FileIsEnding(handle));
}

// --- Quick JSONL extractors (for our fixed schema) ---
double ExtractNumber(const string s, const string key, const string /*term_unused*/)
{
   int p = StringFind(s, key);
   if (p < 0)
      return NaN();
   p += (int)StringLen(key);

   // end at the next comma or closing brace, whichever comes first
   int eComma = StringFind(s, ",", p);
   int eBrace = StringFind(s, "}", p);
   int e = (int)StringLen(s);
   if (eComma >= 0)
      e = MathMin(e, eComma);
   if (eBrace >= 0)
      e = MathMin(e, eBrace);

   string sub = StringSubstr(s, p, e - p);
   StringReplace(sub, "null", "");
   StringTrimLeft(sub);
   StringTrimRight(sub);
   if (sub == "")
      return NaN();
   return (double)StringToDouble(sub);
}

// Extract OID=######## from a position comment
bool ExtractOIDFromComment(const string comment, ulong &oid_out)
{
   oid_out = 0;
   int p = StringFind(comment, "OID=");
   if (p < 0)
      return false;
   p += 4; // after "OID="
   string rest = StringSubstr(comment, p);
   // OID ends at '|' or end of string
   int cut = StringFind(rest, "|");
   if (cut >= 0)
      rest = StringSubstr(rest, 0, cut);
   StringTrimLeft(rest);
   StringTrimRight(rest);
   if (rest == "")
      return false;
   oid_out = (ulong)StringToInteger(rest);
   return (oid_out > 0);
}

// Write (or refresh) the GUI heartbeat timestamp file
void WriteHeartbeatNow()
{
   if (!InpEnableHeartbeat)
      return;

   int now = (int)TimeCurrent();
   if (now == g_lastBeat)
      return;

   int h = FileOpen(g_heartbeat_file, FILE_WRITE | FILE_TXT | FILE_ANSI);
   if (h != INVALID_HANDLE)
   {
      FileSeek(h, 0, SEEK_SET);
      FileWriteString(h, IntegerToString(now));
      FileClose(h);
      g_lastBeat = now;
   }
   else if (InpDebug)
   {
      PrintFormat("[HEARTBEAT] FileOpen failed for '%s' (err=%d)",
                  g_heartbeat_file, GetLastError());
   }
}

// Return true if array 'arr' already contains string 's'
bool _arr_has(const string &arr[], const string s)
{
   for (int i = 0; i < ArraySize(arr); ++i)
      if (arr[i] == s)
         return true;
   return false;
}

// Push unique string to array
void _arr_push_unique(string &arr[], const string s)
{
   if (s == "" || _arr_has(arr, s))
      return;
   int n = ArraySize(arr);
   ArrayResize(arr, n + 1);
   arr[n] = s;
}

// CSV splitter for strings (no fancy quoting)
int SplitCSV(const string csv, string &out[])
{
   ArrayResize(out, 0);
   string s = Trim(csv);
   if (s == "")
      return 0;
   string parts[];
   int n = StringSplit(s, ',', parts);
   for (int i = 0; i < n; i++)
   {
      string p = Trim(parts[i]);
      if (p != "")
      {
         _arr_push_unique(out, p);
      }
   }
   return ArraySize(out);
}

/*
Resolve broker symbol by trying combinations in a sensible order:
  1) Prefix + base + Suffix
  2) base + Suffix
  3) Prefix + base
  4) base
Then for each extra in InpSymbolSuffixVariants (CSV like ".r,+"):
  5) Prefix + base + extra
  6) base + extra
  7) Prefix + base + Suffix + extra
  8) base + Suffix + extra
Returns true and sets 'resolved' when a candidate exists (SymbolSelect succeeds).
*/
bool ResolveBrokerSymbol(const string base, string &resolved)
{
   resolved = "";
   string extras[];
   SplitCSV(InpSymbolSuffixVariants, extras);

   string cands[];
   // primary combos
   _arr_push_unique(cands, InpSymbolPrefix + base + InpSymbolSuffix);
   _arr_push_unique(cands, base + InpSymbolSuffix);
   _arr_push_unique(cands, InpSymbolPrefix + base);
   _arr_push_unique(cands, base);

   // extra suffix variants
   for (int i = 0; i < ArraySize(extras); ++i)
   {
      string x = extras[i];
      _arr_push_unique(cands, InpSymbolPrefix + base + x);
      _arr_push_unique(cands, base + x);
      // also try stacking on top of the configured suffix
      if (StringLen(InpSymbolSuffix) > 0)
      {
         _arr_push_unique(cands, InpSymbolPrefix + base + InpSymbolSuffix + x);
         _arr_push_unique(cands, base + InpSymbolSuffix + x);
      }
   }

   // try in order
   for (int k = 0; k < ArraySize(cands); ++k)
   {
      const string name = cands[k];
      if (SymbolSelect(name, true))
      {
         resolved = name;
         return true;
      }
   }
   return false;
}

//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
int ModifyPositionsForOid(const string broker_symbol, const ulong oid, const double new_sl, const double new_tp)
{
   int changed = 0;
   for (int i = PositionsTotal() - 1; i >= 0; --i)
   {
      if (!g_positionInfo.SelectByIndex(i))
         continue;
      if (g_positionInfo.Symbol() != broker_symbol)
         continue;
      if (g_positionInfo.Magic() != InpMagic)
         continue;

      ulong poid = 0;
      if (!ExtractOIDFromComment(g_positionInfo.Comment(), poid) || poid != oid)
         continue;

      ulong ticket = g_positionInfo.Ticket();
      double cur_sl = g_positionInfo.StopLoss();
      double cur_tp = g_positionInfo.TakeProfit();

      double use_sl = (MathIsValidNumber(new_sl) && new_sl > 0 ? new_sl : cur_sl);
      double use_tp = (MathIsValidNumber(new_tp) && new_tp > 0 ? new_tp : cur_tp);

      if (g_trade.PositionModify(ticket, use_sl, use_tp))
         changed++;
   }
   return changed;
}

//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
int ModifyPendingOrdersForOid(const string broker_symbol, const ulong oid,
                              const double new_sl, const double new_tp)
{
   int changed = 0;

   for (int i = OrdersTotal() - 1; i >= 0; --i)
   {
      ulong ticket = OrderGetTicket(i);
      if (OrderGetString(ORDER_SYMBOL) != broker_symbol)
         continue;
      if (OrderGetInteger(ORDER_MAGIC) != (long)InpMagic)
         continue;

      string cmt = OrderGetString(ORDER_COMMENT);
      ulong ord_oid = 0;
      if (!ExtractOIDFromComment(cmt, ord_oid) || ord_oid != oid)
         continue;

      double price = OrderGetDouble(ORDER_PRICE_OPEN);
      double cur_sl = OrderGetDouble(ORDER_SL);
      double cur_tp = OrderGetDouble(ORDER_TP);

      // read existing order props we must preserve
      ENUM_ORDER_TYPE_TIME time_type = (ENUM_ORDER_TYPE_TIME)OrderGetInteger(ORDER_TYPE_TIME);
      datetime expiration = (datetime)OrderGetInteger(ORDER_TIME_EXPIRATION);
      ENUM_ORDER_TYPE_FILLING fill_type = (ENUM_ORDER_TYPE_FILLING)OrderGetInteger(ORDER_TYPE_FILLING);

      // GTC orders must have expiration=0
      if (time_type == ORDER_TIME_GTC)
         expiration = 0;

      double use_sl = (MathIsValidNumber(new_sl) && new_sl > 0 ? new_sl : cur_sl);
      double use_tp = (MathIsValidNumber(new_tp) && new_tp > 0 ? new_tp : cur_tp);

      if (g_trade.OrderModify(ticket, price, use_sl, use_tp, time_type, expiration, fill_type))
         changed++;
   }
   return changed;
}

//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
bool FindSymbolByOidAll(const ulong oid, string &sym_out)
{
   // positions
   for (int i = PositionsTotal() - 1; i >= 0; --i)
   {
      if (!g_positionInfo.SelectByIndex(i))
         continue;
      if (g_positionInfo.Magic() != InpMagic)
         continue;
      ulong poid = 0;
      if (!ExtractOIDFromComment(g_positionInfo.Comment(), poid))
         continue;
      if (poid == oid)
      {
         sym_out = g_positionInfo.Symbol();
         return true;
      }
   }
   // pending orders
   for (int j = OrdersTotal() - 1; j >= 0; --j)
   {
      ulong t = OrderGetTicket(j);
      if (OrderGetInteger(ORDER_MAGIC) != (long)InpMagic)
         continue;
      ulong o_oid = 0;
      string c = OrderGetString(ORDER_COMMENT);
      if (!ExtractOIDFromComment(c, o_oid))
         continue;
      if (o_oid == oid)
      {
         sym_out = OrderGetString(ORDER_SYMBOL);
         return true;
      }
   }
   return false;
}

//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
bool FindMostRecentSymbolForSource(const string source_key, string &sym_out)
{
   for (int i = ArraySize(g_last_open) - 1; i >= 0; --i)
   {
      if (g_last_open[i].source_key == source_key)
      {
         sym_out = g_last_open[i].symbol;
         return (sym_out != "");
      }
   }
   return false;
}

//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
string BuildTail(const ulong oid, const ulong gid, const string src_tag)
{
   // Always keep OID. Add GID, then SRC only if they fit.
   string out = StringFormat("OID=%I64u", oid);

   string g = StringFormat("|GID=%I64u", gid);
   if (StringLen(out + g) <= 31)
      out += g;

   string s = StringFormat("|SRC=%s", src_tag);
   if (StringLen(out + s) <= 31)
      out += s;

   return out; // <= 31 and OID intact
}

//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
string MakePositionComment(const string base_prefix, const ulong oid, const ulong gid, const string src_tag)
{
   string tail = BuildTail(oid, gid, src_tag);
   string combined = StringFormat("%s|%s", base_prefix, tail);
   if (StringLen(combined) <= 31)
      return combined;
   return tail; // drop the pretty prefix if it doesn't fit
}

//+------------------------------------------------------------------+
//| Break-Even structure Implementation                              |
//+------------------------------------------------------------------+

struct BeTracker
{
   ulong oid;
   string symbol;
   double trigger_price;
   bool is_buy;
   bool applied;
   datetime created;
};
BeTracker g_be_trackers[];

//+------------------------------------------------------------------+
//| Store BE trigger when opening positions                          |
//+------------------------------------------------------------------+
void StoreBeTrigger(ulong oid, const string symbol, double trigger_price, bool is_buy)
{
   // Check if already exists
   for (int i = 0; i < ArraySize(g_be_trackers); i++)
   {
      if (g_be_trackers[i].oid == oid)
      {
         g_be_trackers[i].trigger_price = trigger_price;
         g_be_trackers[i].is_buy = is_buy;
         return;
      }
   }

   // Add new tracker
   int n = ArraySize(g_be_trackers);
   ArrayResize(g_be_trackers, n + 1);
   g_be_trackers[n].oid = oid;
   g_be_trackers[n].symbol = symbol;
   g_be_trackers[n].trigger_price = trigger_price;
   g_be_trackers[n].is_buy = is_buy;
   g_be_trackers[n].applied = false;
   g_be_trackers[n].created = TimeCurrent();

   // Also store in GlobalVariable as backup
   GlobalVariableSet(StringFormat("BE_TRG_%I64u", oid), trigger_price);
   GlobalVariableSet(StringFormat("BE_SIDE_%I64u", oid), is_buy ? 1.0 : 0.0);

   if (InpDebug)
      PrintFormat("[BE] Stored trigger: OID=%I64u, Symbol=%s, Trigger=%.5f, Side=%s",
                  oid, symbol, trigger_price, is_buy ? "BUY" : "SELL");
}

//+------------------------------------------------------------------+
//| Check and apply break-even based on current price                |
//+------------------------------------------------------------------+
void CheckAndApplyBreakEven()
{
   if (!InpBE_Enable)
      return;

   for (int i = 0; i < ArraySize(g_be_trackers); i++)
   {
      if (g_be_trackers[i].applied)
         continue;

      // Direct access to array element fields
      string symbol = g_be_trackers[i].symbol;
      double trigger_price = g_be_trackers[i].trigger_price;
      bool is_buy = g_be_trackers[i].is_buy;
      ulong oid = g_be_trackers[i].oid;

      // If symbol wasn't known (e.g., loaded from GV), discover it from open positions
      if (g_be_trackers[i].symbol == "" || g_be_trackers[i].symbol == NULL)
      {
         for (int p = PositionsTotal() - 1; p >= 0; --p)
         {
            if (!g_positionInfo.SelectByIndex(p))
               continue;
            if (g_positionInfo.Magic() != InpMagic)
               continue;

            ulong poid = 0;
            if (!ExtractOIDFromComment(g_positionInfo.Comment(), poid))
               continue;
            if (poid != g_be_trackers[i].oid)
               continue;

            g_be_trackers[i].symbol = g_positionInfo.Symbol();
            g_be_trackers[i].is_buy = (g_positionInfo.PositionType() == POSITION_TYPE_BUY);
            break;
         }
      }
      if (g_be_trackers[i].symbol == "" || g_be_trackers[i].symbol == NULL)
         continue; // still unknown, try next time

      // Get current price
      MqlTick tick;
      if (!SymbolInfoTick(symbol, tick))
         continue;

      double current_price = is_buy ? tick.bid : tick.ask;

      // Check if trigger hit
      bool trigger_hit = false;
      if (is_buy)
         trigger_hit = (current_price >= trigger_price);
      else
         trigger_hit = (current_price <= trigger_price);

      if (!trigger_hit)
         continue;

      // Apply BE to all positions with this OID
      int positions_modified = 0;
      double point = SymbolInfoDouble(symbol, SYMBOL_POINT);
      double be_offset = InpBE_OffsetPoints * point;

      for (int j = PositionsTotal() - 1; j >= 0; j--)
      {
         if (!g_positionInfo.SelectByIndex(j))
            continue;
         if (g_positionInfo.Magic() != InpMagic)
            continue;
         if (g_positionInfo.Symbol() != symbol)
            continue;

         // Check if position has this OID
         ulong pos_oid = 0;
         if (!ExtractOIDFromComment(g_positionInfo.Comment(), pos_oid))
            continue;
         if (pos_oid != oid)
            continue;

         // Calculate new SL (entry + optional offset)
         double entry_price = g_positionInfo.PriceOpen();
         double new_sl = entry_price;

         if (InpBE_OffsetPoints != 0)
         {
            new_sl = is_buy ? (entry_price + be_offset) : (entry_price - be_offset);
         }

         // Modify position
         ulong ticket = g_positionInfo.Ticket();
         double current_tp = g_positionInfo.TakeProfit();

         if (g_trade.PositionModify(ticket, new_sl, current_tp))
         {
            positions_modified++;
            if (InpBE_Logging)
            {
               PrintFormat("[BE] Modified: Ticket=%I64u, OID=%I64u, NewSL=%.5f (Entry=%.5f, Offset=%d points)",
                           ticket, oid, new_sl, entry_price, InpBE_OffsetPoints);
            }
         }
      }

      if (positions_modified > 0)
      {
         g_be_trackers[i].applied = true; // Direct array access
         GlobalVariableSet(StringFormat("BE_APPLIED_%I64u", oid), TimeCurrent());

         PrintFormat("[BE] SUCCESS: Trigger %.5f hit on %s. Modified %d positions to BE for OID=%I64u",
                     trigger_price, symbol, positions_modified, oid);

         if (InpSoundAlerts)
            PlaySound("ok.wav");
      }
   }
}

//-------------------------------------------------------------------------------
// OpenMultiPositions
//  - Opens 1..N legs based on TPs and settings
//  - Applies BE trigger at chosen TP index (from InpBE_TriggerTP or be_on_tp override)
//  - Respects InpSkipBadTPs, InpRiskPerLeg, InpPositionsToOpen, InpMaxPositions
//  - Routes MARKET vs PENDING from 'order_type' or legacy (entry presence)
// Returns number of successfully opened legs.
//-------------------------------------------------------------------------------
int OpenMultiPositions(
    const string source_key,    // stable per-channel key (for last-ID tracking externally)
    const string source,        // human/channel name (for tags)
    const string order_type,    // "MARKET" | "LIMIT" | "STOP" | ""(legacy auto)
    const ulong oid,            // signal id (OID)
    const ulong gid,            // optional group id
    const string broker_symbol, // final broker symbol (with prefix/suffix)
    const bool is_buy,          // side
    double entry,               // may be <=0 for market
    const double sl,            // 0/<=0 means no SL (lot sizing falls back if needed)
    const string tps_csv,       // CSV list of TP prices
    const int be_on_tp,         // 0 = off; >0 = override which TP triggers BE
    const double risk_pc,       // risk% from signal (NaN/<=0 -> use InpRiskPercent)
    const double lots_fix,      // fixed lots if >0
    const double risk_mul,      // risk multiplier (>=0 or NaN)
    const string risk_label     // "half"|"quarter"|"double" (case-insensitive)
)
{
   // Safety: trading switches
   if (is_buy && !InpAllowBuys)
   {
      if (InpDebug)
         Print("[OPEN] Buys disabled");
      return 0;
   }
   if (!is_buy && !InpAllowSells)
   {
      if (InpDebug)
         Print("[OPEN] Sells disabled");
      return 0;
   }

   // Ensure symbol is selected
   if (!SymbolSelect(broker_symbol, true))
   {
      Print("Symbol select failed: ", broker_symbol, " (add it to Market Watch)");
      return 0;
   }
   g_sym.Name(broker_symbol);
   g_sym.Refresh();

   // Pull live price reference
   MqlTick tk;
   SymbolInfoTick(broker_symbol, tk);
   const double live_ref = (is_buy ? tk.ask : tk.bid);
   const double ref_entry = (MathIsValidNumber(entry) && entry > 0.0) ? entry : live_ref;

   // Parse TP list and direction-filter/sort
   double tps_raw[];
   ParseCSVDoubles(tps_csv, tps_raw);

   double tps_use[];
   for (int i = 0; i < ArraySize(tps_raw); ++i)
   {
      const bool okdir = is_buy ? (tps_raw[i] > ref_entry) : (tps_raw[i] < ref_entry);
      if (okdir || !InpSkipBadTPs)
      {
         const int n = ArraySize(tps_use);
         ArrayResize(tps_use, n + 1);
         tps_use[n] = tps_raw[i];
      }
   }
   ArraySort(tps_use); // ascending
   if (!is_buy)        // for sells, make descending
   {
      const int n = ArraySize(tps_use);
      for (int i = 0; i < n / 2; ++i)
      {
         double tmp = tps_use[i];
         tps_use[i] = tps_use[n - 1 - i];
         tps_use[n - 1 - i] = tmp;
      }
   }

   const int tp_count = ArraySize(tps_use);
   const int max_allowed = MathMax(1, MathMin(10, InpMaxPositions));
   int num_positions = 1;

   if (InpPositionsToOpen > 0)
      num_positions = MathMax(1, MathMin(InpPositionsToOpen, max_allowed));
   else
      num_positions = MathMax(1, MathMin(tp_count > 0 ? tp_count : 1, max_allowed));

   // Choose TP per leg
   double leg_tp_prices[];
   ArrayResize(leg_tp_prices, num_positions);
   for (int i = 0; i < num_positions; ++i)
      leg_tp_prices[i] = (i < tp_count ? tps_use[i] : 0.0);

   // Decide total lots (fixed -> risk-based -> default), then normalize & cap
   double total_lots = 0.0;
   string lots_reason = "";

   // NEW: Check if using custom lots per TP
   if (InpUseCustomLots)
   {
      // When using custom lots, we don't calculate total_lots here
      // We'll assign per leg below
      lots_reason = "custom_per_tp";
   }
   else
   {
      // Original logic: compute total lots
      if (!ComputeLotsForSignal(
              broker_symbol, is_buy,
              (MathIsValidNumber(entry) && entry > 0.0 ? entry : 0.0),
              sl, lots_fix, risk_pc, risk_mul, risk_label,
              total_lots, lots_reason))
      {
         if (InpDebug)
            PrintFormat("[OPEN] lot sizing failed (%s)", lots_reason);
         return 0;
      }

      total_lots = NormalizeLot(broker_symbol, MathMin(total_lots, MaxLotForSymbol(broker_symbol)));
      if (total_lots <= 0.0)
      {
         if (InpDebug)
            Print("[OPEN] total_lots<=0");
         return 0;
      }
   }

   // Calculate lot distribution per leg
   double leg_lots[];
   ArrayResize(leg_lots, num_positions);

   if (InpUseCustomLots)
   {
      // Use custom lots per TP
      for (int i = 0; i < num_positions; i++)
      {
         double custom_lot = 0.0;

         switch (i)
         {
         case 0:
            custom_lot = InpTP1_Lots;
            break;
         case 1:
            custom_lot = InpTP2_Lots;
            break;
         case 2:
            custom_lot = InpTP3_Lots;
            break;
         case 3:
            custom_lot = InpTP4_Lots;
            break;
         default:
            custom_lot = InpTP5_Lots;
            break;
         }

         // Normalize and cap
         custom_lot = NormalizeLot(broker_symbol, custom_lot);
         custom_lot = MathMin(custom_lot, MaxLotForSymbol(broker_symbol));

         leg_lots[i] = custom_lot;

         if (InpDebug)
            PrintFormat("[OPEN] TP%d: Custom lot=%.2f", i + 1, leg_lots[i]);
      }
   }
   else
   {
      // Original behavior: equal distribution or per-leg
      double lot_each = InpRiskPerLeg
                            ? total_lots
                            : total_lots / num_positions;

      for (int i = 0; i < num_positions; i++)
      {
         leg_lots[i] = NormalizeLot(broker_symbol, lot_each);
         leg_lots[i] = MathMin(leg_lots[i], MaxLotForSymbol(broker_symbol));
      }
   }

   // Decide BE trigger TP (signal override first, then user input)
   int trigger_tp = 0;
   if (be_on_tp > 0)
      trigger_tp = be_on_tp;
   else
      trigger_tp = InpBE_TriggerTP;

   int trigger_idx = -1; // 0-based index into tps_use
   double trigger_price = 0.0;

   if (InpBE_Enable && trigger_tp > 0 && tp_count > 0)
   {
      const int desired = MathMin(trigger_tp, tp_count); // clamp to available TPs
      trigger_idx = desired - 1;
      trigger_price = tps_use[trigger_idx];
      // Store one tracker per OID—actual BE move is handled in CheckAndApplyBreakEven()
      StoreBeTrigger(oid, broker_symbol, trigger_price, is_buy);
      if (InpBE_Logging)
         PrintFormat("[BE] Trigger TP%d=%.5f set for OID=%I64u on %s", desired, trigger_price, oid, broker_symbol);
   }

   // Decide routing
   string ot_up = order_type;
   StringToUpper(ot_up);
   const bool force_market = (ot_up == "MARKET");
   const bool force_pending = (ot_up == "LIMIT" || ot_up == "STOP");
   const bool legacy_has_entry = (MathIsValidNumber(entry) && entry > 0.0);

   bool do_market = false;
   bool do_pending = false;
   if (force_market)
      do_market = true;
   else if (force_pending)
      do_pending = true;
   else
   {
      do_pending = legacy_has_entry;
      do_market = !legacy_has_entry;
   }

   // Optional conflict close
   if (InpCloseConflicts)
      CloseOpposite(broker_symbol, is_buy);

   // Ready to send
   g_trade.SetExpertMagicNumber(InpMagic);
   g_trade.SetDeviationInPoints(InpSlippagePoints);

   int successful_trades = 0;
   for (int pos_idx = 0; pos_idx < num_positions; ++pos_idx)
   {
      const double tp_price = leg_tp_prices[pos_idx];
      const double lot_per_position = leg_lots[pos_idx];

      if (lot_per_position <= 0.0)
      {
         if (InpDebug)
            PrintFormat("[OPEN] Skipping TP%d: lot_per_position<=0", pos_idx + 1);
         continue;
      }

      // Comment base + compact tail
      string base_comment;
      if (pos_idx < tp_count && tp_price > 0.0)
         base_comment = StringFormat("TSC_%s_TP%d", is_buy ? "B" : "S", pos_idx + 1);
      else
         base_comment = StringFormat("TSC_%s_X%d", is_buy ? "B" : "S", pos_idx + 1);

      // Cosmetic "_BE" on the leg that matches the trigger TP
      const bool add_be_flag = (trigger_idx >= 0 && pos_idx == trigger_idx && tp_price > 0.0);
      if (add_be_flag)
         base_comment += "_BE";

      string source_tag = GenerateSourceTag(source);
      string position_comment = MakePositionComment(base_comment, oid, gid, source_tag);

      // Place order
      bool ok = false;
      double sl_price = (MathIsValidNumber(sl) && sl > 0.0) ? sl : 0.0;

      if (do_market)
      {
         if (is_buy)
            ok = g_trade.Buy(lot_per_position, broker_symbol, g_sym.Ask(), sl_price, tp_price, position_comment);
         else
            ok = g_trade.Sell(lot_per_position, broker_symbol, g_sym.Bid(), sl_price, tp_price, position_comment);
      }
      else if (do_pending)
      {
         ok = PlacePending(g_trade, is_buy, broker_symbol, lot_per_position, ref_entry, sl_price, tp_price, position_comment);
      }

      if (InpDebug)
         PrintFormat("ROUTE: %s %s [%s] TP%d entry=%.5f -> %s  cmt='%s' lots=%.2f %s",
                     (is_buy ? "BUY" : "SELL"), broker_symbol, (StringLen(ot_up) == 0 ? "LEGACY" : ot_up),
                     pos_idx + 1, entry, (do_market ? "MARKET" : (do_pending ? "PENDING" : "SKIP")),
                     position_comment, lot_per_position,
                     (InpUseCustomLots ? "[CUSTOM]" : "[" + lots_reason + "]"));

      if (ok)
         successful_trades++;
      Sleep(100); // mild throttle
   }

   if (successful_trades > 0)
   {
      // Remember source for this OID so CLOSE events can attribute properly
      RememberOidSource(oid, source, GenerateSourceTag(source));
      if (InpAlertOnOpen)
         PlaySound("ok.wav");

      PrintFormat("FSC MULTI: %d/%d %s %s opened (OID=%I64u) %s",
                  successful_trades, num_positions, (is_buy ? "BUY" : "SELL"), broker_symbol, oid,
                  InpRiskPerLeg ? "[RiskPerLeg]" : "[RiskPerSignal]");
   }
   else
   {
      PrintFormat("FSC FAILED: No %s %s positions opened (OID=%I64u)", (is_buy ? "BUY" : "SELL"), broker_symbol, oid);
   }

   return successful_trades;
}

//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
void RememberOidSource(const ulong oid, const string source, const string tag)
{
   for (int i = 0; i < ArraySize(g_oid_keys); ++i)
   {
      if (g_oid_keys[i] == oid)
      {
         g_oid_sources[i] = source;
         g_oid_tags[i] = tag;
         return;
      }
   }
   int n = ArraySize(g_oid_keys);
   ArrayResize(g_oid_keys, n + 1);
   ArrayResize(g_oid_sources, n + 1);
   ArrayResize(g_oid_tags, n + 1);
   g_oid_keys[n] = oid;
   g_oid_sources[n] = source;
   g_oid_tags[n] = tag;
}

//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
void ApplyBreakEvenForOid(const string sym, const ulong oid)
{
   if (!InpBE_Enable || oid == 0)
      return;

   double point = SymbolInfoDouble(sym, SYMBOL_POINT);
   long ldigs = 0;
   SymbolInfoInteger(sym, SYMBOL_DIGITS, ldigs);
   int digs = (int)ldigs;
   double off = (InpBE_OffsetPoints == 0 ? 0.0 : InpBE_OffsetPoints * point);

   int applied = 0;
   for (int i = PositionsTotal() - 1; i >= 0; --i)
   {
      if (!g_positionInfo.SelectByIndex(i))
         continue;
      if (g_positionInfo.Magic() != InpMagic)
         continue;
      if (g_positionInfo.Symbol() != sym)
         continue;

      // must belong to this OID
      ulong oid2 = 0;
      if (!ExtractOIDFromComment(g_positionInfo.Comment(), oid2) || oid2 != oid)
         continue;

      const ulong ticket = g_positionInfo.Ticket();
      const bool is_buy = (g_positionInfo.PositionType() == POSITION_TYPE_BUY);
      const double open_px = g_positionInfo.PriceOpen();
      const double cur_tp = g_positionInfo.TakeProfit();

      double new_sl = open_px;
      if (InpBE_OffsetPoints != 0)
         new_sl = is_buy ? (open_px + off) : (open_px - off);

      bool ok = g_trade.PositionModify(ticket, new_sl, cur_tp);
      if (InpBE_Logging)
         PrintFormat("[BE][TP-event] OID=%I64u ticket=%I64u -> SL=%.*f %s",
                     oid, ticket, digs, new_sl, ok ? "OK" : "FAIL");
      if (ok)
         applied++;
   }

   if (applied > 0)
   {
      GlobalVariableSet(StringFormat("BE_APPLIED_%I64u", oid), TimeCurrent());
      if (InpBE_Logging)
         PrintFormat("[BE][TP-event] Applied to %d legs on %s (OID=%I64u)", applied, sym, oid);
   }
}

//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
string Canon(const string sym_raw)
{
   string s = sym_raw;
   StringToUpper(s);

   // strip dot-suffix like ".a"
   int dot = StringFind(s, ".");
   if (dot > 0)
      s = StringSubstr(s, 0, dot);

   // strip configured prefix/suffix (defensive; after uppercasing)
   string p = InpSymbolPrefix;
   StringToUpper(p);
   string q = InpSymbolSuffix;
   StringToUpper(q);

   if (StringLen(p) > 0 && StringFind(s, p) == 0)
      s = StringSubstr(s, StringLen(p));

   if (StringLen(q) > 0)
   {
      int pos = StringLen(s) - StringLen(q);
      if (pos >= 0 && StringFind(s, q, pos) == pos)
         s = StringSubstr(s, 0, pos);
   }
   return s;
}

// ---- Time window helpers (server time) ----
int g_start_min = 0; // minutes since 00:00
int g_end_min = 1439;

//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
int ParseHHMM(const string s) // returns minutes since midnight, clamp 0..1439
{
   string t = s;
   StringTrimLeft(t);
   StringTrimRight(t);
   int colon = StringFind(t, ":");
   int h = 0, m = 0;
   if (colon >= 0)
   {
      h = (int)StringToInteger(StringSubstr(t, 0, colon));
      m = (int)StringToInteger(StringSubstr(t, colon + 1));
   }
   else
   {
      // allow "H" or "HHMM" fallbacks (optional)
      if (StringLen(t) <= 2)
      {
         h = (int)StringToInteger(t);
         m = 0;
      }
      else
      {
         string hs = StringSubstr(t, 0, StringLen(t) - 2);
         string ms = StringSubstr(t, StringLen(t) - 2);
         h = (int)StringToInteger(hs);
         m = (int)StringToInteger(ms);
      }
   }
   h = (int)MathMax(0, MathMin(23, h));
   m = (int)MathMax(0, MathMin(59, m));
   return h * 60 + m;
}

//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
bool IsDayAllowed(int dow) // MQL5 DayOfWeek(): 0=Sun..6=Sat
{
   switch (dow)
   {
   case 0:
      return InpTradeSunday;
   case 1:
      return InpTradeMonday;
   case 2:
      return InpTradeTuesday;
   case 3:
      return InpTradeWednesday;
   case 4:
      return InpTradeThursday;
   case 5:
      return InpTradeFriday;
   case 6:
      return InpTradeSaturday;
   }
   return true;
}

//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
bool IsWithinWindowNow()
{
   // use broker/server time so it matches charts/symbol session
   datetime now = TimeCurrent(); // or TimeTradeServer()
   MqlDateTime dt;
   TimeToStruct(now, dt);
   int dow = dt.day_of_week; // 0..6 (Sun..Sat)
   if (!IsDayAllowed(dow))
      return false;

   int minutes = dt.hour * 60 + dt.min; // 0..1439

   // handle normal window (start <= end) and overnight window (start > end)
   if (g_start_min <= g_end_min)
      return (minutes >= g_start_min && minutes <= g_end_min);
   else
      return (minutes >= g_start_min || minutes <= g_end_min);
}

//+------------------------------------------------------------------+
//| Cleanup old BE trackers (optional, call periodically)            |
//+------------------------------------------------------------------+
void CleanupOldBeTrackers()
{
   datetime cutoff = TimeCurrent() - 86400 * 7; // Keep for 7 days

   for (int i = ArraySize(g_be_trackers) - 1; i >= 0; i--)
   {
      if (g_be_trackers[i].applied && g_be_trackers[i].created < cutoff)
      {
         // Clean up GlobalVariables too
         GlobalVariableDel(StringFormat("BE_TRG_%I64u", g_be_trackers[i].oid));
         GlobalVariableDel(StringFormat("BE_SIDE_%I64u", g_be_trackers[i].oid));
         GlobalVariableDel(StringFormat("BE_APPLIED_%I64u", g_be_trackers[i].oid));

         // Remove from array
         for (int j = i; j < ArraySize(g_be_trackers) - 1; j++)
         {
            g_be_trackers[j] = g_be_trackers[j + 1];
         }
         ArrayResize(g_be_trackers, ArraySize(g_be_trackers) - 1);
      }
   }
}

//+------------------------------------------------------------------+
//| Load existing BE trackers                                        |
//+------------------------------------------------------------------+
void LoadBeTrackers()
{
   int total = GlobalVariablesTotal();
   for (int i = 0; i < total; i++)
   {
      string name = GlobalVariableName(i);
      if (StringFind(name, "BE_TRG_") == 0)
      {
         // Extract OID from name
         string oid_str = StringSubstr(name, 7); // After "BE_TRG_"
         ulong oid = (ulong)StringToInteger(oid_str);

         if (oid > 0)
         {
            // Check if not already applied
            if (!GlobalVariableCheck(StringFormat("BE_APPLIED_%I64u", oid)))
            {
               double trigger = GlobalVariableGet(name);
               double side_val = GlobalVariableGet(StringFormat("BE_SIDE_%I64u", oid));

               // Reconstruct tracker (symbol unknown, will be checked against all positions)
               int n = ArraySize(g_be_trackers);
               ArrayResize(g_be_trackers, n + 1);
               g_be_trackers[n].oid = oid;
               g_be_trackers[n].symbol = ""; // Will be filled when positions are found
               g_be_trackers[n].trigger_price = trigger;
               g_be_trackers[n].is_buy = (side_val > 0.5);
               g_be_trackers[n].applied = false;
               g_be_trackers[n].created = TimeCurrent();

               if (InpDebug)
                  PrintFormat("[BE] Loaded tracker: OID=%I64u, Trigger=%.5f", oid, trigger);
            }
         }
      }
   }
}

//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
bool FindOidSource(const ulong oid, string &source_out, string &tag_out)
{
   for (int i = ArraySize(g_oid_keys) - 1; i >= 0; --i)
   {
      if (g_oid_keys[i] == oid)
      {
         source_out = g_oid_sources[i];
         tag_out = g_oid_tags[i];
         return true;
      }
   }
   return false;
}

// ---- utils: write one JSON line to MQL5\Files\Fluent_signals.jsonl
void WriteJsonLine(const string json)
{
   int h = FileOpen(InpSignalFileName,
                    FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_READ | FILE_SHARE_READ);
   if (h != INVALID_HANDLE)
   {
      FileSeek(h, 0, SEEK_END);
      FileWriteString(h, json + "\r\n");
      FileFlush(h);
      FileClose(h);
   }
}

//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
string JsonEscape(const string s)
{
   string out = s;
   StringReplace(out, "\\", "\\\\");
   StringReplace(out, "\"", "\\\"");
   return out;
}

//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
string DealReasonToStr(ENUM_DEAL_REASON r)
{
   switch (r)
   {
   case DEAL_REASON_SL:
      return "SL";
   case DEAL_REASON_TP:
      return "TP";
   case DEAL_REASON_SO:
      return "StopOut";
   case DEAL_REASON_CLIENT:
      return "Manual";
   case DEAL_REASON_MOBILE:
      return "Mobile";
   case DEAL_REASON_WEB:
      return "Web";
   case DEAL_REASON_EXPERT:
      return "EA";
   case DEAL_REASON_ROLLOVER:
      return "Rollover";
   case DEAL_REASON_VMARGIN:
      return "Margin";
   case DEAL_REASON_SPLIT:
      return "Split";
   default:
      return "Other";
   }
}

//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
string ExtractString(const string s, const string key, const string endDelim)
{
   int p = StringFind(s, key);
   if (p >= 0)
      p += (int)StringLen(key);
   else
   {
      string k2 = key;
      StringReplace(k2, "\":\"", "\": \"");
      p = StringFind(s, k2);
      if (p < 0)
         return "";
      p += (int)StringLen(k2);
   }
   int e = (endDelim == "") ? (int)StringLen(s) : StringFind(s, endDelim, p);
   if (e < 0)
      e = (int)StringLen(s);
   return StringSubstr(s, p, e - p);
}

//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
ulong ExtractULongQuoted(const string s, const string key)
{
   int p = StringFind(s, key);
   if (p >= 0)
      p += (int)StringLen(key);
   else
   {
      string k2 = key;
      StringReplace(k2, "\":\"", "\": \"");
      p = StringFind(s, k2);
      if (p < 0)
         return 0;
      p += (int)StringLen(k2);
   }
   int e = StringFind(s, "\"", p);
   if (e < 0)
      return 0;
   string sub = StringSubstr(s, p, e - p);
   return (ulong)StringToInteger(sub);
}

//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
int ParseCSVDoubles(const string csv, double &out[])
{
   ArrayResize(out, 0);
   string scsv = Trim(csv);
   if (scsv == "")
      return 0;
   string parts[];
   int n = StringSplit(scsv, (ushort)StringGetCharacter(",", 0), parts);
   for (int i = 0; i < n; i++)
   {
      double v = (double)StringToDouble(Trim(parts[i]));
      int sz = ArraySize(out);
      ArrayResize(out, sz + 1);
      out[sz] = v;
   }
   return ArraySize(out);
}

//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
bool IsBuySide(string side)
{
   string up = side;
   StringToUpper(up);
   return StringFind(up, "BUY") == 0;
}

// -------- Connection & Trading Status Checks --------
bool CheckTradingAllowed()
{
   if (!TerminalInfoInteger(TERMINAL_CONNECTED))
   {
      Print("[ERROR] Terminal not connected to broker!");
      return false;
   }

   if (!AccountInfoInteger(ACCOUNT_TRADE_ALLOWED))
   {
      Print("[ERROR] Trading not allowed on this account!");
      return false;
   }

   if (!AccountInfoInteger(ACCOUNT_TRADE_EXPERT))
   {
      Print("[ERROR] Expert trading not allowed!");
      return false;
   }

   if (!MQLInfoInteger(MQL_TRADE_ALLOWED))
   {
      Print("[ERROR] Automated trading disabled in terminal!");
      return false;
   }

   return true;
}

// -------- Heartbeat Monitor --------
void CheckHeartbeat()
{
   if (!InpEnableHeartbeat)
      return;

   // Try open heartbeat file
   int handle = FileOpen(g_heartbeat_file, FILE_READ | FILE_TXT | FILE_SHARE_READ);
   if (handle == INVALID_HANDLE)
   {
      // First run: note that we haven't seen any heartbeat yet, but don't spam
      if (g_last_heartbeat == 0)
      {
         if (InpDebug)
            Print("[HEARTBEAT] No heartbeat file found yet");
         g_last_heartbeat = TimeCurrent(); // start a reference so stale timer can work
      }
      return;
   }

   // Read timestamp
   string timestamp_str = FileReadString(handle);
   FileClose(handle);

   // Guard against malformed content
   long ts_long = 0;
   bool ts_ok = true;
   if (StringLen(timestamp_str) == 0)
      ts_ok = false;
   else
   {
      // Only digits expected
      for (int i = 0; i < (int)StringLen(timestamp_str); ++i)
      {
         ushort ch = StringGetCharacter(timestamp_str, i);
         if (ch < '0' || ch > '9')
         {
            ts_ok = false;
            break;
         }
      }
      if (ts_ok)
         ts_long = (long)StringToInteger(timestamp_str);
   }

   if (ts_ok)
   {
      datetime heartbeat_time = (datetime)ts_long;
      if (heartbeat_time > g_last_heartbeat)
      {
         g_last_heartbeat = heartbeat_time;
         if (InpDebug)
            PrintFormat("[HEARTBEAT] GUI alive at %s", TimeToString(heartbeat_time));
      }
   }
   else
   {
      // Bad content; just log once in a while via stale path below
      if (InpDebug)
         PrintFormat("[HEARTBEAT] Malformed heartbeat content: '%s'", timestamp_str);
   }

   // Stale check
   int elapsed = (int)(TimeCurrent() - g_last_heartbeat);
   if (elapsed > InpHeartbeatTimeout && !g_emergency_mode)
   {
      static datetime last_warning = 0;
      int interval = MathMax(30, InpHeartbeatWarnInterval); // hard min 30s to avoid spam
      if ((TimeCurrent() - last_warning) >= interval)
      {
         string msg = StringFormat("WARNING: GUI heartbeat stale for %d seconds (timeout=%d)",
                                   elapsed, InpHeartbeatTimeout);

         // Optional popup
         if (InpHeartbeatPopupAlerts)
            Alert(msg);

         // Optional sound piggybacks on global alert switch
         if (InpHeartbeatPopupAlerts && InpSoundAlerts)
            PlaySound("alert.wav");

         // Always print if enabled (recommended)
         if (InpHeartbeatPrintWarnings)
            Print("[WARNING] ", msg);

         last_warning = TimeCurrent();
      }
   }
}

// -------- Position Snapshot Writer --------
void WritePositionSnapshot()
{
   if (!InpWriteSnapshots)
      return;

   // throttle I/O
   if (TimeCurrent() - g_last_snapshot < 2)
      return;
   g_last_snapshot = TimeCurrent();

   int handle = FileOpen(g_snapshot_file, FILE_WRITE | FILE_TXT | FILE_SHARE_READ);
   if (handle == INVALID_HANDLE)
   {
      if (InpDebug)
         Print("[SNAPSHOT] Failed to open file for writing");
      return;
   }

   string json = "[\n";
   bool first = true;
   bool only_magic = InpSnapshotOnlyMagic;

   for (int i = 0; i < PositionsTotal(); i++)
   {
      if (!g_positionInfo.SelectByIndex(i))
         continue;
      if (only_magic && g_positionInfo.Magic() != InpMagic)
         continue;

      string sym = g_positionInfo.Symbol();
      long ldigs;
      if (!SymbolInfoInteger(sym, SYMBOL_DIGITS, ldigs))
         ldigs = (long)Digits(); // fallback just in case
      int digs = (int)ldigs;

      if (!first)
         json += ",\n";
      first = false;

      json += "  {\n";
      json += StringFormat("    \"ticket\": %lld,\n", g_positionInfo.Ticket());
      json += StringFormat("    \"symbol\": \"%s\",\n", sym);
      json += StringFormat("    \"type\": \"%s\",\n", g_positionInfo.PositionType() == POSITION_TYPE_BUY ? "BUY" : "SELL");
      json += StringFormat("    \"volume\": %.2f,\n", g_positionInfo.Volume());
      json += StringFormat("    \"open_price\": %.*f,\n", digs, g_positionInfo.PriceOpen());
      json += StringFormat("    \"current_price\": %.*f,\n", digs, g_positionInfo.PriceCurrent());
      json += StringFormat("    \"sl\": %.*f,\n", digs, g_positionInfo.StopLoss());
      json += StringFormat("    \"tp\": %.*f,\n", digs, g_positionInfo.TakeProfit());
      json += StringFormat("    \"profit\": %.2f,\n", g_positionInfo.Profit());
      json += StringFormat("    \"comment\": \"%s\",\n", g_positionInfo.Comment());
      json += StringFormat("    \"open_time\": %lld\n", g_positionInfo.Time());
      json += "  }";
   }

   json += "\n]";

   FileWriteString(handle, json);
   FileClose(handle);

   if (InpDebug)
      PrintFormat("[SNAPSHOT] Written %d positions", PositionsTotal());
}

// -------- Per-channel last-id via Global Variables --------
string SanitizeChannelName(const string channel_name)
{
   string s = channel_name;
   StringReplace(s, " ", "_");
   StringReplace(s, "📈", "CHART");
   StringReplace(s, "💎", "DIAMOND");
   StringReplace(s, "-", "_");
   StringReplace(s, "/", "_");
   StringReplace(s, "\\", "_");
   StringReplace(s, ":", "_");
   StringReplace(s, "@", "_");
   return s;
}

//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
string MakeSourceKey(const string source, const string source_id)
{
   if (StringLen(source_id) > 0)
      return "id_" + source_id;
   string s = source;
   StringToLower(s);
   return "name_" + s;
}

//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
ulong GetChannelLastID(const string channel_key)
{
   string key = "TSC_LASTID_" + SanitizeChannelName(channel_key);
   if (GlobalVariableCheck(key))
      return (ulong)GlobalVariableGet(key);
   return 0;
}

//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
void SetChannelLastID(const string channel_key, const ulong new_id)
{
   string key = "TSC_LASTID_" + SanitizeChannelName(channel_key);
   GlobalVariableSet(key, (double)new_id);
   if (InpDebug)
      PrintFormat("Updated channel '%s' last_id=%I64u", channel_key, new_id);
}

//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
void LoadChannelStates()
{
   Print("Loading channel states (from Global Variables)...");
   int total = (int)GlobalVariablesTotal();
   for (int i = 0; i < total; ++i)
   {
      string name = GlobalVariableName(i);
      if (StringFind(name, "TSC_LASTID_") == 0)
      {
         ulong last_id = (ulong)GlobalVariableGet(name);
         PrintFormat("  '%s': last_id=%I64u", name, last_id);
      }
   }
}

//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
void PrintChannelStats()
{
   Print("=== CHANNEL STATISTICS ===");
   int total = (int)GlobalVariablesTotal();
   for (int i = 0; i < total; ++i)
   {
      string name = GlobalVariableName(i);
      if (StringFind(name, "TSC_LASTID_") == 0)
      {
         ulong last_id = (ulong)GlobalVariableGet(name);
         PrintFormat("Channel: '%s'  Last ID: %I64u", name, last_id);
      }
   }
   Print("========================");
}

// -------- Track last OPEN id per (source_key, broker_symbol) --------
struct LastOpenRec
{
   string source_key;
   string symbol;
   ulong open_id;
   datetime when;
};
LastOpenRec g_last_open[];

//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
ulong GetLastOpenId(const string source_key, const string broker_symbol)
{
   for (int i = ArraySize(g_last_open) - 1; i >= 0; --i)
   {
      if (g_last_open[i].source_key == source_key && g_last_open[i].symbol == broker_symbol)
         return g_last_open[i].open_id;
   }
   return 0;
}

//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
void SetLastOpenId(const string source_key, const string broker_symbol, const ulong oid)
{
   for (int i = 0; i < ArraySize(g_last_open); ++i)
   {
      if (g_last_open[i].source_key == source_key && g_last_open[i].symbol == broker_symbol)
      {
         g_last_open[i].open_id = oid;
         g_last_open[i].when = TimeCurrent();
         return;
      }
   }
   int n = ArraySize(g_last_open);
   ArrayResize(g_last_open, n + 1);
   g_last_open[n].source_key = source_key;
   g_last_open[n].symbol = broker_symbol;
   g_last_open[n].open_id = oid;
   g_last_open[n].when = TimeCurrent();
}

//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
bool CommentHasOID(const string comment, const ulong oid)
{
   string tag = StringFormat("OID=%I64u", oid);
   return (StringFind(comment, tag) >= 0);
}

// -------- Classification / caps / risk calc --------
enum SymClass
{
   SYM_FX,
   SYM_METAL,
   SYM_OIL,
   SYM_INDEX,
   SYM_CRYPTO,
   SYM_OTHER
};

//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
SymClass ClassifySymbol(const string sym)
{
   string s = sym;
   StringToUpper(s);
   if (StringFind(s, "XTIUSD") >= 0 || StringFind(s, "USOIL") >= 0 || StringFind(s, "XBRUSD") >= 0 || StringFind(s, "UKOIL") >= 0)
      return SYM_OIL;
   if (StringFind(s, "XAU") >= 0 || StringFind(s, "XAG") >= 0)
      return SYM_METAL;
   if (StringFind(s, "BTC") >= 0 || StringFind(s, "ETH") >= 0 || StringFind(s, "CRYPTO") >= 0)
      return SYM_CRYPTO;
   if (StringFind(s, "US30") >= 0 || StringFind(s, "DJ") >= 0 || StringFind(s, "NAS") >= 0 || StringFind(s, "SPX") >= 0 || StringFind(s, "US500") >= 0 || StringFind(s, "DE40") >= 0 || StringFind(s, "GER") >= 0 || StringFind(s, "UK100") >= 0 || StringFind(s, "JP225") >= 0)
      return SYM_INDEX;
   if (StringLen(s) == 6)
      return SYM_FX;
   return SYM_OTHER;
}

//+------------------------------------------------------------------+
//| MAx Lots for Symbols                                             |
//+------------------------------------------------------------------+
double MaxLotForSymbol(const string sym_raw)
{
   string sym = Canon(sym_raw);
   double m = InpMaxLotOverall;
   switch (ClassifySymbol(sym))
   {
   case SYM_METAL:
      m = MathMin(m, InpMaxLot_Metal);
      break;
   case SYM_OIL:
      m = MathMin(m, InpMaxLot_Oil);
      break;
   case SYM_INDEX:
      m = MathMin(m, InpMaxLot_Index);
      break;
   case SYM_FX:
      m = MathMin(m, InpMaxLot_FX);
      break;
   case SYM_CRYPTO:
      m = MathMin(m, InpMaxLot_Crypto);
      break;
   default:; // keep overall
   }
   return m;
}

//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
double NormalizeLot(const string sym, double lot)
{
   double minlot = SymbolInfoDouble(sym, SYMBOL_VOLUME_MIN);
   double maxlot = SymbolInfoDouble(sym, SYMBOL_VOLUME_MAX);
   double step = SymbolInfoDouble(sym, SYMBOL_VOLUME_STEP);
   if (step <= 0.0)
      step = 0.01;
   lot = MathMax(minlot, MathMin(maxlot, lot));
   return MathFloor(lot / step) * step;
}

//------------------------------------------------------------------------------
// Point 5 helper: decide final lots (fixed -> risk-based -> default),
// with label/multiplier handling, caps, and normalization.
// Returns true if a positive lot was produced; false otherwise.
//------------------------------------------------------------------------------
bool ComputeLotsForSignal(
    const string sym,
    const bool is_buy,
    double entry_price,           // may be 0/NaN -> we'll pick bid/ask
    const double sl_price,        // price (not distance); <=0 means "no SL"
    const double lots_fixed,      // if >0, takes precedence
    const double risk_percent_in, // from JSON; may be NaN/<=0
    const double risk_multiplier, // numeric multiplier (>=0 or NaN)
    string risk_label,            // "half"/"quarter"/"double" (case-insensitive)
    double &out_lots,             // result (normalized & capped)
    string &out_reason            // short reason code for logs/UI
)
{
   out_lots = 0.0;
   out_reason = "";

   // 1) Fixed lots
   if (MathIsValidNumber(lots_fixed) && lots_fixed > 0.0)
   {
      double cap = MaxLotForSymbol(sym);
      out_lots = NormalizeLot(sym, MathMin(lots_fixed, cap));
      out_reason = "fixed";
      return (out_lots > 0.0);
   }

   // 2) Risk-based (requires SL)
   if (MathIsValidNumber(sl_price) && sl_price > 0.0)
   {
      // Base risk%
      double use_risk = (MathIsValidNumber(risk_percent_in) && risk_percent_in > 0.0)
                            ? risk_percent_in
                            : InpRiskPercent;

      // Multiplier
      if (MathIsValidNumber(risk_multiplier) && risk_multiplier > 0.0)
         use_risk *= risk_multiplier;

      // Friendly labels
      if (StringLen(risk_label) > 0)
      {
         StringToLower(risk_label);
         if (StringFind(risk_label, "half") >= 0)
            use_risk *= 0.5;
         else if (StringFind(risk_label, "quarter") >= 0)
            use_risk *= 0.25;
         else if (StringFind(risk_label, "double") >= 0)
            use_risk *= 2.0;
      }

      // If entry not provided, take the live price in the correct side
      MqlTick tk;
      SymbolInfoTick(sym, tk);
      if (!MathIsValidNumber(entry_price) || entry_price <= 0.0)
         entry_price = (is_buy ? tk.ask : tk.bid);

      // Distance (points) from entry to SL
      const double point = SymbolInfoDouble(sym, SYMBOL_POINT);
      const double tick_val = SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_VALUE);
      const double tick_size = SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_SIZE);
      if (point <= 0.0 || tick_val <= 0.0 || tick_size <= 0.0)
      {
         out_reason = "sym_meta";
         return false;
      }

      const double dist_pts = MathAbs(entry_price - sl_price) / point;
      if (dist_pts <= 0.0 || !MathIsValidNumber(dist_pts))
      {
         out_reason = "bad_sl";
         return false;
      }

      // Value-per-point per lot (account currency)
      const double vpppl = tick_val / (tick_size / point);
      if (vpppl <= 0.0 || !MathIsValidNumber(vpppl))
      {
         out_reason = "vpppl";
         return false;
      }

      // Money risked
      double risk_money = g_acc.Balance() * (use_risk / 100.0);
      if (InpRiskDollarCap > 0.0)
         risk_money = MathMin(risk_money, InpRiskDollarCap);

      if (risk_money <= 0.0)
      {
         out_reason = "zero_risk";
         return false;
      }

      // Lots = risk / (distance * value-per-point-per-lot)
      double lots = risk_money / (dist_pts * vpppl);

      // Normalize & cap
      lots = NormalizeLot(sym, lots);
      lots = MathMin(lots, MaxLotForSymbol(sym));

      if (lots > 0.0 && MathIsValidNumber(lots))
      {
         out_lots = lots;
         out_reason = "risk";
         return true;
      }
   }

   // 3) Fallback to default
   double lots_def = NormalizeLot(sym, MathMin(InpDefaultLots, MaxLotForSymbol(sym)));
   if (lots_def > 0.0)
   {
      out_lots = lots_def;
      out_reason = "default";
      return true;
   }

   out_reason = "none";
   return false;
}

void RefreshRates(const string symbol_name)
{
   MqlTick tk;
   SymbolInfoTick(symbol_name, tk);
}

// -------- Emergency Close All --------
int EmergencyCloseAll()
{
   g_emergency_mode = true;
   int closed = 0;

   Print("!!! EMERGENCY CLOSE ALL ACTIVATED !!!");
   Alert("EMERGENCY STOP: Closing all positions!");

   // Close all positions
   for (int i = PositionsTotal() - 1; i >= 0; --i)
   {
      if (!g_positionInfo.SelectByIndex(i))
         continue;
      if (g_positionInfo.Magic() != InpMagic)
         continue;

      ulong ticket = g_positionInfo.Ticket();
      string symbol = g_positionInfo.Symbol();

      if (g_trade.PositionClose(ticket))
      {
         closed++;
         PrintFormat("[EMERGENCY] Closed position %I64u on %s", ticket, symbol);
      }
      else
      {
         PrintFormat("[EMERGENCY] FAILED to close position %I64u on %s", ticket, symbol);
      }
   }

   // Delete all pending orders
   for (int i = OrdersTotal() - 1; i >= 0; --i)
   {
      ulong ticket = OrderGetTicket(i);
      if (OrderGetInteger(ORDER_MAGIC) == InpMagic)
      {
         if (g_trade.OrderDelete(ticket))
         {
            closed++;
            PrintFormat("[EMERGENCY] Deleted pending order %I64u", ticket);
         }
      }
   }

   g_positions_closed_emergency = closed;

   // Sound alert
   if (InpSoundAlerts && InpAlertOnEmergency && closed > 0)
   {
      PlaySound("alert2.wav");
      Sleep(500);
      PlaySound("alert2.wav");
   }

   Alert(StringFormat("EMERGENCY STOP COMPLETE: %d positions/orders closed", closed));

   return closed;
}

// -------- Utilities --------
void CloseOpposite(const string symbol_name, const bool entering_buy)
{
   for (int i = PositionsTotal() - 1; i >= 0; --i)
   {
      if (!g_positionInfo.SelectByIndex(i))
         continue;
      if (g_positionInfo.Symbol() != symbol_name)
         continue;
      if (g_positionInfo.Magic() != InpMagic)
         continue;

      long type = g_positionInfo.PositionType();
      if (entering_buy && type == POSITION_TYPE_SELL)
      {
         if (InpDebug)
            PrintFormat("CloseOpposite: closing SELL %s ticket=%I64u", symbol_name, g_positionInfo.Ticket());
         g_trade.PositionClose(g_positionInfo.Ticket());
      }
      if (!entering_buy && type == POSITION_TYPE_BUY)
      {
         if (InpDebug)
            PrintFormat("CloseOpposite: closing BUY %s ticket=%I64u", symbol_name, g_positionInfo.Ticket());
         g_trade.PositionClose(g_positionInfo.Ticket());
      }
   }
}

//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
bool PlacePending(CTrade &trade, const bool is_buy, const string symbol_name, const double vol,
                  const double price, const double sl, const double tp, const string comment)
{
   RefreshRates(symbol_name);
   double ask = SymbolInfoDouble(symbol_name, SYMBOL_ASK);
   double bid = SymbolInfoDouble(symbol_name, SYMBOL_BID);
   bool ok = false;
   if (is_buy)
   {
      if (price > ask)
         ok = trade.BuyStop(vol, price, symbol_name, sl, tp, ORDER_TIME_GTC, 0, comment);
      else
         ok = trade.BuyLimit(vol, price, symbol_name, sl, tp, ORDER_TIME_GTC, 0, comment);
   }
   else
   {
      if (price < bid)
         ok = trade.SellStop(vol, price, symbol_name, sl, tp, ORDER_TIME_GTC, 0, comment);
      else
         ok = trade.SellLimit(vol, price, symbol_name, sl, tp, ORDER_TIME_GTC, 0, comment);
   }
   return ok;
}

// -------- Diagnostics --------
void PrintAccountInfo()
{
   Print("=== ACCOUNT INFORMATION ===");
   Print("Account number: ", AccountInfoInteger(ACCOUNT_LOGIN));
   Print("Account name: ", AccountInfoString(ACCOUNT_NAME));
   Print("Account server: ", AccountInfoString(ACCOUNT_SERVER));
   Print("Account company: ", AccountInfoString(ACCOUNT_COMPANY));
   Print("Account currency: ", AccountInfoString(ACCOUNT_CURRENCY));
   Print("Account leverage: ", AccountInfoInteger(ACCOUNT_LEVERAGE));
   Print("Account margin mode: ", AccountInfoInteger(ACCOUNT_MARGIN_MODE));
   Print("Account trade allowed: ", AccountInfoInteger(ACCOUNT_TRADE_ALLOWED));
   Print("Account trade expert: ", AccountInfoInteger(ACCOUNT_TRADE_EXPERT));
   Print("Account margin call level: ", AccountInfoDouble(ACCOUNT_MARGIN_SO_CALL));
   Print("Account margin stop out level: ", AccountInfoDouble(ACCOUNT_MARGIN_SO_SO));

   // Enhanced status checking
   if (!TerminalInfoInteger(TERMINAL_CONNECTED))
      Print("*** WARNING: Terminal NOT connected to broker! ***");
   else
      Print("Terminal connection: OK");

   if (!AccountInfoInteger(ACCOUNT_TRADE_ALLOWED))
      Print("*** WARNING: Trading is not allowed on this account! ***");
   if (!AccountInfoInteger(ACCOUNT_TRADE_EXPERT))
      Print("*** WARNING: Expert trading is not allowed on this account! ***");
   else
      Print("Expert trading: ENABLED");

   if (!MQLInfoInteger(MQL_TRADE_ALLOWED))
      Print("*** WARNING: Automated trading disabled in terminal! ***");
   else
      Print("Automated trading: ENABLED");

   Print("Balance: ", AccountInfoDouble(ACCOUNT_BALANCE));
   Print("Equity: ", AccountInfoDouble(ACCOUNT_EQUITY));
   Print("Free margin: ", AccountInfoDouble(ACCOUNT_MARGIN_FREE));
   Print("========================");
}

//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
void OnTradeTransaction(const MqlTradeTransaction &trans,
                        const MqlTradeRequest &req,
                        const MqlTradeResult &res)
{
   // Debug: see every transaction type
   if (InpDebug)
      PrintFormat("[TX] type=%d deal=%I64u", trans.type, trans.deal);

   if (trans.type != TRADE_TRANSACTION_DEAL_ADD)
      return;

   // Make sure the history window includes this deal
   datetime now = TimeCurrent();
   // using a small window around 'now' is usually fine;
   // you can also use DEAL_TIME after we fetch it once
   HistorySelect(now - 3600, now + 60);

   long entry = (long)HistoryDealGetInteger(trans.deal, DEAL_ENTRY);
   if (InpDebug)
      PrintFormat("[TX] entry=%d (want %d=DEAL_ENTRY_OUT)", entry, DEAL_ENTRY_OUT);
   if (entry != DEAL_ENTRY_OUT)
      return;

   // Pull deal fields
   string symbol = (string)HistoryDealGetString(trans.deal, DEAL_SYMBOL);
   double profit = HistoryDealGetDouble(trans.deal, DEAL_PROFIT); // account currency (USD on your acct)
   long pos_id = (long)HistoryDealGetInteger(trans.deal, DEAL_POSITION_ID);
   string comment = (string)HistoryDealGetString(trans.deal, DEAL_COMMENT);
   ENUM_DEAL_REASON rsn = (ENUM_DEAL_REASON)HistoryDealGetInteger(trans.deal, DEAL_REASON);
   datetime deal_ts = (datetime)HistoryDealGetInteger(trans.deal, DEAL_TIME);

   // ---- Recover tags from compact 31-char comment ----
   string c_low = comment;
   StringToLower(c_low);

   string oid = "";
   string gid_s = "";
   string source = ""; // IMPORTANT: no default "EA"

   // OID
   int p = StringFind(c_low, "oid=");
   if (p >= 0)
   {
      string tail = StringSubstr(comment, p + 4);
      int cut = StringFind(tail, "|");
      oid = (cut >= 0 ? StringSubstr(tail, 0, cut) : tail);
   }

   // GID
   p = StringFind(c_low, "gid=");
   if (p >= 0)
   {
      string tail = StringSubstr(comment, p + 4);
      int cut = StringFind(tail, "|");
      gid_s = (cut >= 0 ? StringSubstr(tail, 0, cut) : tail);
   }

   // SRC (or SOURCE) — avoid reusing 'p' with side effects
   int idx_src = StringFind(c_low, "src=");
   int idx_source = StringFind(c_low, "source=");
   int idx = (idx_src >= 0 ? idx_src : idx_source);
   int adv = (idx_src >= 0 ? 4 : (idx_source >= 0 ? 7 : 0));

   if (idx >= 0)
   {
      string tail = StringSubstr(comment, idx + adv);
      int cut = StringFind(tail, "|");
      source = (cut >= 0 ? StringSubstr(tail, 0, cut) : tail);
   }

   // --- Fallback: resolve from OID remembered at OPEN ---
   if (source == "" && StringLen(oid) > 0)
   {
      ulong oid_num = (ulong)StringToInteger(oid);
      if (oid_num > 0)
      {
         string src2 = "", tag2 = "";
         if (FindOidSource(oid_num, src2, tag2))
         {
            // Prefer full channel name for correct aggregation
            source = (src2 != "" ? src2 : tag2);
         }
      }
   }

   // Optional: if source is an internal label, blank it so UI can hide it
   if (source == "EA" || source == "GUI" || source == "WEB")
      source = "";

   string reason = DealReasonToStr(rsn);

   // Build JSON (CLOSE record)
   int t = (int)TimeCurrent();
   string json = StringFormat(
       "{\"action\":\"CLOSE\",\"source\":\"%s\",\"symbol\":\"%s\",\"t\":%d,"
       "\"profit_usd\":%.2f,\"ticket\":\"%I64d\",\"oid\":\"%s\",\"gid\":\"%s\",\"reason\":\"%s\"}",
       JsonEscape(source), symbol, t, profit, trans.deal,
       JsonEscape(oid), JsonEscape(gid_s), DealReasonToStr(rsn));

   if (InpDebug)
      Print("[CLOSE->JSON] ", json);
   WriteJsonLine(json);

   // Event-driven Break-Even on TP:
   if (InpBE_Enable && rsn == DEAL_REASON_TP)
   {
      ulong oid_num = (ulong)StringToInteger(oid);
      if (oid_num > 0 &&
          !GlobalVariableCheck(StringFormat("BE_APPLIED_%I64u", oid_num)))
      {
         ApplyBreakEvenForOid(symbol, oid_num);
      }
   }
}

// -------- Main signal loop (JSONL) --------
void ProcessNewSignals()
{
   // Check trading status first
   if (!CheckTradingAllowed())
   {
      static datetime last_trade_warning = 0;
      if (TimeCurrent() - last_trade_warning > 60)
      {
         Print("[WARNING] Trading not allowed - check terminal settings");
         last_trade_warning = TimeCurrent();
      }
      return;
   }

   int handle = FileOpen(InpSignalFileName, FILE_READ | FILE_BIN | FILE_SHARE_READ);
   if (handle == INVALID_HANDLE)
   {
      if (InpDebug)
         Print("FileOpen failed: ", InpSignalFileName, " err=", GetLastError());
      return;
   }

   string line;
   int signals_processed = 0;

   while (ReadLineUtf8(handle, line))
   {
      string s = Trim(line);
      if (s == "")
         continue;

      // -------- HEADER: extraction --------
      string action = ExtractString(s, "\"action\": \"", "\"");
      ulong id = ExtractULongQuoted(s, "\"id\": \"");

      // Skip incomplete/partial lines without advancing anything
      if (action == "" || id == 0)
      {
         if (InpDebug)
            Print("[SKIP] Incomplete line (no action/id)");
         continue;
      }

      // Identify the source first, then build a stable per-channel key
      string source = ExtractString(s, "\"source\": \"", "\"");
      string source_id = ExtractString(s, "\"source_id\": \"", "\"");
      string source_key = MakeSourceKey(source, source_id);
      string source_tag = GenerateSourceTag(source);
      ulong gid = ExtractULongQuoted(s, "\"gid\": \"");

      ulong channel_last_id = GetChannelLastID(source_key);

      // Treat MODIFY / EDIT / UPDATE / CORRECTION as "edit-like"
      string act_up = action;
      StringToUpper(act_up);
      bool is_edit_like = (act_up == "MODIFY" || StringFind(act_up, "EDIT") >= 0 || StringFind(act_up, "UPDATE") >= 0 || StringFind(act_up, "CORRECTION") >= 0);

      // If it's not edit-like, enforce monotonic id
      if (id <= channel_last_id && !is_edit_like)
      {
         if (InpDebug)
            PrintFormat("SKIP: channel_key='%s' id=%I64u <= last_id=%I64u", source_key, id, channel_last_id);
         continue;
      }

      // -------- Safe to parse the rest now --------
      string side = ExtractString(s, "\"side\": \"", "\"");
      string symbol = ExtractString(s, "\"symbol\": \"", "\"");
      double entry = ExtractNumber(s, "\"entry\":", ",");
      double sl = ExtractNumber(s, "\"sl\":", ",");
      string tps_csv = ExtractString(s, "\"tps_csv\": \"", "\"");
      int be_on_tp = (int)ExtractNumber(s, "\"be_on_tp\":", ",");
      double risk_pc = ExtractNumber(s, "\"risk_percent\":", ",");
      double lots_fix = ExtractNumber(s, "\"lots\":", ",");
      double risk_mul = ExtractNumber(s, "\"risk_multiplier\":", ",");
      string risk_label = ExtractString(s, "\"risk_label\": \"", "\"");
      string new_tps = ExtractString(s, "\"new_tps_csv\": \"", "\"");
      double new_sl = ExtractNumber(s, "\"new_sl\":", ",");
      ulong close_oid = ExtractULongQuoted(s, "\"oid\": \"");
      string order_type = ExtractString(s, "\"order_type\": \"", "\"");
      string ot_up = order_type;
      StringToUpper(ot_up);
      string a_up = action;
      StringToUpper(a_up);

      if (InpDebug)
         PrintFormat("PARSED id=%I64u action=%s side=%s symbol=%s source='%s' source_key='%s' tag=%s entry=%.5f sl=%.5f tps=%s",
                     id, action, side, symbol, source, source_key, source_tag, entry, sl, tps_csv);

      // infer symbol for edit-like when missing
      if (a_up != "EMERGENCY_CLOSE_ALL" && symbol == "")
      {
         if (is_edit_like)
         {
            ulong guess_oid = close_oid;
            if (guess_oid > 0 && FindSymbolByOidAll(guess_oid, symbol))
            {
               if (InpDebug)
                  PrintFormat("[MODIFY] Inferred symbol '%s' by OID=%I64u", symbol, guess_oid);
            }
            else if (FindMostRecentSymbolForSource(source_key, symbol))
            {
               if (InpDebug)
                  PrintFormat("[MODIFY] Inferred symbol '%s' by last-open for '%s'", symbol, source_key);
            }
         }
         if (symbol == "")
         {
            if (InpDebug)
               Print("[SKIP] Cannot infer symbol for edit-like message; leaving last_id unchanged");
            continue;
         }
      }

      // Build broker symbol once
      string broker_symbol = "";
      if (!ResolveBrokerSymbol(symbol, broker_symbol))
      {
         if (InpDebug)
         {
            Print("=== SYMBOL DEBUG (resolution failed) ===");
            Print("Base symbol: ", symbol);
            Print("Prefix: '", InpSymbolPrefix, "'  Suffix: '", InpSymbolSuffix, "'");
            Print("Extras CSV: '", InpSymbolSuffixVariants, "'");
            Print("Show the correct symbol in Market Watch if it exists.");
            Print("=======================================");
         }
         Print("Symbol resolution failed: ", symbol, " (check Market Watch / prefix/suffix variants)");
         continue; // do NOT advance last_id
      }

      // For OPEN we need g_sym attached; others we just make sure it’s visible
      bool need_symbol_selected = (a_up == "OPEN");
      if (need_symbol_selected)
      {
         SymbolSelect(broker_symbol, true); // Resolve already selects; be safe
         g_sym.Name(broker_symbol);
         g_sym.Refresh();
      }
      else
      {
         SymbolSelect(broker_symbol, true); // best-effort
      }

      // ===== EMERGENCY CLOSE ALL =====
      if (a_up == "EMERGENCY_CLOSE_ALL")
      {
         string confirm = ExtractString(s, "\"confirm\": \"", "\"");
         if (confirm == "YES")
         {
            int closed = EmergencyCloseAll();
            PrintFormat("[EMERGENCY] Closed %d positions/orders", closed);
         }
         // advance only if newer
         ulong prev = GetChannelLastID(source_key);
         if (id > prev)
            SetChannelLastID(source_key, id);

         signals_processed++;
         continue;
      }

      // ===== CLOSE =====
      if (a_up == "CLOSE")
      {
         ulong target_oid = (close_oid > 0 ? close_oid : GetLastOpenId(source_key, broker_symbol));
         if (InpDebug)
            PrintFormat("CLOSE for %s from '%s' -> target OID=%I64u", broker_symbol, source, target_oid);

         if (target_oid == 0)
         {
            if (InpDebug)
               Print("No OID available; nothing to close.");
            continue; // don’t advance
         }

         bool any = false;
         int closed_count = 0;
         for (int i = PositionsTotal() - 1; i >= 0; --i)
         {
            if (!g_positionInfo.SelectByIndex(i))
               continue;
            if (g_positionInfo.Symbol() != broker_symbol)
               continue;
            if (g_positionInfo.Magic() != InpMagic)
               continue;

            string pcmt = g_positionInfo.Comment();
            if (!CommentHasOID(pcmt, target_oid))
               continue;

            ulong tik = g_positionInfo.Ticket();
            bool ok = g_trade.PositionClose(tik);
            if (InpDebug)
               PrintFormat("  Close ticket=%I64u OID=%I64u -> %s", tik, target_oid, ok ? "OK" : "FAIL");
            if (ok)
            {
               any = true;
               closed_count++;
            }
         }

         if (any)
         {
            PrintFormat("TSC CLOSE: closed %d positions for %s (OID=%I64u) from %s",
                        closed_count, broker_symbol, target_oid, source);
            if (InpAlertOnClose)
               PlaySound("ok.wav");
         }
         else
         {
            PrintFormat("TSC CLOSE: no matching OID positions for %s (OID=%I64u) from %s",
                        broker_symbol, target_oid, source);
         }

         // advance only if newer
         ulong prev = GetChannelLastID(source_key);
         if (id > prev)
            SetChannelLastID(source_key, id);

         signals_processed++;
         continue;
      }

      // ===== MODIFY (SL / TP for positions AND pending orders) =====
      if (a_up == "MODIFY")
      {
         if (InpDebug)
            PrintFormat("MODIFY for %s from '%s' new_sl=%.5f new_tps=%s", broker_symbol, source, new_sl, new_tps);

         // Parse new TP list; use first TP as “TP1” for late-TP simplicity
         double tps_new[];
         int tp_new_count = ParseCSVDoubles(new_tps, tps_new);
         double tp1 = (tp_new_count > 0 ? tps_new[0] : 0.0);

         // Decide target OID
         ulong target_oid = (close_oid > 0 ? close_oid : GetLastOpenId(source_key, broker_symbol));
         if (target_oid == 0)
         {
            if (InpDebug)
               Print("MODIFY: no OID found for ", broker_symbol, " from ", source);
            continue; // do not advance last_id
         }

         // Arm BE if TP1 appears late
         if (InpBE_Enable && (InpBE_AutoOnTP1 || be_on_tp > 0) && tp1 > 0.0 && !GlobalVariableCheck(StringFormat("BE_APPLIED_%I64u", target_oid)))
         {
            bool is_buy = true;
            bool found_side = false;
            for (int i = PositionsTotal() - 1; i >= 0; --i)
            {
               if (!g_positionInfo.SelectByIndex(i))
                  continue;
               if (g_positionInfo.Symbol() != broker_symbol)
                  continue;
               if (g_positionInfo.Magic() != InpMagic)
                  continue;
               ulong poid = 0;
               if (!ExtractOIDFromComment(g_positionInfo.Comment(), poid) || poid != target_oid)
                  continue;
               is_buy = (g_positionInfo.PositionType() == POSITION_TYPE_BUY);
               found_side = true;
               break;
            }
            if (!found_side && side != "")
               is_buy = IsBuySide(side);
            StoreBeTrigger(target_oid, broker_symbol, tp1, is_buy);
            if (InpDebug)
               PrintFormat("[BE][MODIFY] Armed BE trigger for OID=%I64u at TP1=%.5f", target_oid, tp1);
         }

         // Apply to positions and, if none, to pendings
         double tp_to_apply = (tp_new_count == 1 ? tp1 : 0.0);
         int pos_changed = ModifyPositionsForOid(broker_symbol, target_oid, new_sl, tp_to_apply);
         int ord_changed = (pos_changed == 0 ? ModifyPendingOrdersForOid(broker_symbol, target_oid, new_sl, tp_to_apply) : 0);

         if (pos_changed > 0 || ord_changed > 0)
         {
            if (InpDebug)
               PrintFormat("TSC MODIFY: updated %d positions and %d pending orders for %s (OID=%I64u)",
                           pos_changed, ord_changed, broker_symbol, target_oid);
            if (InpAlertOnModify && InpSoundAlerts)
               PlaySound("ok.wav");
         }
         else
         {
            PrintFormat("TSC MODIFY: no matching positions/orders to modify for %s (OID=%I64u)", broker_symbol, target_oid);
         }

         // Only advance last_id if this id is newer  (you already had this)
         ulong prev = GetChannelLastID(source_key);
         if (id > prev)
            SetChannelLastID(source_key, id);

         signals_processed++;
         continue;
      }

      // ===== OPEN (multi-position) =====
      if (side == "")
      {
         if (InpDebug)
            Print("SKIP: empty side");
         continue;
      }
      const bool is_buy = IsBuySide(side);

      // (Optional) time/day filter here if you put it outside:
      if (InpTimeFilter && !IsWithinWindowNow())
      {
         if (InpDebug)
            PrintFormat("[TIME] OPEN blocked for %s on %s (id=%I64u)",
                        broker_symbol, TimeToString(TimeCurrent()), id);

         // IMPORTANT: Advance last_id so we don't retry this signal later
         ulong prev = GetChannelLastID(source_key);
         if (id > prev)
            SetChannelLastID(source_key, id);

         signals_processed++;
         continue;
      }

      int opened = OpenMultiPositions(
          /*source_key*/ source_key,
          /*source*/ source,
          /*order_type*/ order_type, // "", "MARKET", "LIMIT", "STOP"
          /*oid*/ id,
          /*gid*/ gid,
          /*broker_sym*/ broker_symbol,
          /*is_buy*/ is_buy,
          /*entry*/ entry,
          /*sl*/ sl,
          /*tps_csv*/ tps_csv,
          /*be_on_tp*/ (int)be_on_tp,
          /*risk_pc*/ risk_pc,
          /*lots_fix*/ lots_fix,
          /*risk_mul*/ risk_mul,
          /*risk_label*/ risk_label);

      if (opened > 0)
      {
         SetLastOpenId(source_key, broker_symbol, id);
         SetChannelLastID(source_key, id); // advance only after success
         signals_processed++;
      }
      else
      {
         // don’t advance last_id on failure
      }
   }

   FileClose(handle);

   //+------------------------------------------------------------------+
   //|                                                                  |
   //+------------------------------------------------------------------+
   if (signals_processed > 0)
      PrintFormat("Processed %d signals this cycle", signals_processed);
}

//+------------------------------------------------------------------+
//| Expert init                                                      |
//+------------------------------------------------------------------+
int OnInit()
{
   LoadChannelStates();

   // Reset emergency mode
   g_emergency_mode = false;
   g_positions_closed_emergency = 0;

   // Initialize heartbeat
   g_last_heartbeat = TimeCurrent();

   EventSetTimer(HeartbeatSeconds);
   WriteHeartbeatNow();

   g_start_min = ParseHHMM(InpStartTimeHHMM);
   g_end_min = ParseHHMM(InpEndTimeHHMM);
   if (InpDebug)
      PrintFormat("[TIME] Filter=%s  window=%02d:%02d–%02d:%02d  Days: Mon=%d Tue=%d Wed=%d Thu=%d Fri=%d Sat=%d Sun=%d",
                  InpTimeFilter ? "ON" : "OFF",
                  g_start_min / 60, g_start_min % 60, g_end_min / 60, g_end_min % 60,
                  InpTradeMonday, InpTradeTuesday, InpTradeWednesday, InpTradeThursday,
                  InpTradeFriday, InpTradeSaturday, InpTradeSunday);

   Print("=== Fluent Signal Copier Ready ===");
   Print("File: ", InpSignalFileName);
   Print("Multi-Position Mode: ENABLED (Max ", InpMaxPositions, " positions per signal)");
   Print("Per-Channel ID Tracking: GlobalVariables");
   Print("Heartbeat Monitor: ", InpEnableHeartbeat ? "ENABLED" : "DISABLED");
   Print("Position Snapshots: ", InpWriteSnapshots ? "ENABLED" : "DISABLED");
   Print("Sound Alerts: ", InpSoundAlerts ? "ENABLED" : "DISABLED");
   Print("Source Tags: ", InpSourceTags ? "ENABLED" : "DISABLED");
   Print("EMERGENCY STOP: Ready (action: EMERGENCY_CLOSE_ALL)");
   Print("PositionsToOpen: ", (InpPositionsToOpen > 0 ? (string)IntegerToString(InpPositionsToOpen) : "AUTO"));
   Print("Risk Mode: ", InpRiskPerLeg ? "Per-Leg (scales with leg count)" : "Per-Signal (split across legs)");

   PrintAccountInfo();
   PrintChannelStats();

   // Initial snapshot
   WritePositionSnapshot();

   // Load BE Tracker
   LoadBeTrackers();

   return (INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
//| Expert deinit                                                    |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   EventKillTimer();

   // Final snapshot
   WritePositionSnapshot();

   Print("=== Fluent Signal Copier Stopped ===");
   if (g_positions_closed_emergency > 0)
      PrintFormat("Emergency positions closed in this session: %d", g_positions_closed_emergency);
   PrintChannelStats();
}

//+------------------------------------------------------------------+
//| Expert OnTick                                                    |
//+------------------------------------------------------------------+
void OnTick()
{
   // Write position snapshot periodically
   WritePositionSnapshot();
}

//+------------------------------------------------------------------+
//| Expert OnTimer                                                   |
//+------------------------------------------------------------------+
void OnTimer()
{
   // Check heartbeat
   CheckHeartbeat();

   // Write heartbeat file
   WriteHeartbeatNow();

   // Process signals
   ProcessNewSignals();

   // Check and apply break-even
   CheckAndApplyBreakEven();

   // Periodic cleanup of old BE trackers (default every 60 min)
   static datetime last_be_cleanup = 0;
   int cleanup_period_sec = MathMax(300, InpBE_CleanupEveryMin * 60); // hard min 5 min
   if (TimeCurrent() - last_be_cleanup >= cleanup_period_sec)
   {
      CleanupOldBeTrackers();
      last_be_cleanup = TimeCurrent();
      if (InpDebug)
         PrintFormat("[BE] Cleanup run completed (interval=%d sec)", cleanup_period_sec);
   }

   // Write position snapshot
   WritePositionSnapshot();
}
//+------------------------------------------------------------------+
