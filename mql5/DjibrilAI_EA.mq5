//+------------------------------------------------------------------+
//| DjibrilAI_EA.mq5 — Main Expert Advisor                            |
//| Reads geopolitical AI signals and executes WTI/Brent trades.      |
//| Part of Djibril AI Trading System v1.0                             |
//+------------------------------------------------------------------+
#property copyright "Djibril AI / ExMachina Trading Systems"
#property link      "https://github.com/e49nana"
#property version   "1.00"
#property description "AI-powered crude oil trading based on geopolitical analysis"
#property strict

//--- Includes
#include "Include\\SignalBridge.mqh"
#include "Include\\RiskManager.mqh"
#include <Trade\Trade.mqh>

//+------------------------------------------------------------------+
//| Input Parameters                                                  |
//+------------------------------------------------------------------+
input group "=== Signal Settings ==="
input string   InpSignalDir       = "signals";        // Signal files directory
input int      InpSignalTimeout   = 300;               // Signal max age (seconds)
input double   InpMinConfidence   = 0.60;              // Minimum signal confidence

input group "=== Risk Settings ==="
input int      InpMagicNumber     = 202503;            // Magic number
input double   InpMaxRiskPct      = 0.05;              // Max risk per trade (fraction)
input double   InpMaxDrawdownPct  = 0.15;              // Max drawdown before stop (fraction)
input int      InpMaxSpread       = 50;                // Max spread (points)
input int      InpMaxPositions    = 2;                 // Max simultaneous positions

input group "=== Session Filter ==="
input int      InpSessionStartH   = 8;                 // Session start (UTC hour)
input int      InpSessionEndH     = 20;                // Session end (UTC hour)
input bool     InpUseSessionFilter = true;             // Enable session filter

input group "=== Trailing Stop ==="
input bool     InpUseTrailing     = true;              // Enable ATR trailing stop
input double   InpTrailATRMult    = 0.8;               // Trailing ATR multiplier
input bool     InpUseBreakeven    = true;              // Move SL to breakeven at 1:1
input bool     InpUsePartialClose = true;              // Close 50% at intermediate TP
input double   InpPartialPct      = 0.50;              // Partial close percentage

input group "=== Display ==="
input bool     InpShowPanel       = true;              // Show info panel
input color    InpPanelColor      = clrDarkSlateGray;  // Panel background color

//+------------------------------------------------------------------+
//| Global Variables                                                  |
//+------------------------------------------------------------------+
CSignalBridge  g_bridge;
CRiskManager   g_risk;
CTrade         g_trade;

OilSignal      g_last_signal;
string         g_last_signal_id = "";
bool           g_trading_enabled = true;
int            g_atr_handle = INVALID_HANDLE;
double         g_atr_buffer[];

//+------------------------------------------------------------------+
//| Expert initialization                                             |
//+------------------------------------------------------------------+
int OnInit()
  {
   // Validate symbol
   string sym = _Symbol;
   if(StringFind(sym, "XTI") < 0 && StringFind(sym, "WTI") < 0 &&
      StringFind(sym, "CL") < 0 && StringFind(sym, "OIL") < 0 &&
      StringFind(sym, "USOIL") < 0 && StringFind(sym, "BRN") < 0 &&
      StringFind(sym, "XBR") < 0 && StringFind(sym, "BRENT") < 0)
     {
      Print("[DjibrilAI] WARNING: Symbol ", sym, " may not be crude oil. Proceeding anyway.");
     }

   // Configure signal bridge
   g_bridge.SetSignalDir(InpSignalDir);
   g_bridge.SetMaxAgeSec(InpSignalTimeout);

   // Configure risk manager
   g_risk.SetMaxRiskPct(InpMaxRiskPct);
   g_risk.SetMaxDrawdownPct(InpMaxDrawdownPct);
   g_risk.SetMaxSpread(InpMaxSpread);
   g_risk.SetMagicNumber(InpMagicNumber);
   g_risk.SetMaxPositions(InpMaxPositions);
   g_risk.Initialize(sym);

   // Configure trade
   g_trade.SetExpertMagicNumber(InpMagicNumber);
   g_trade.SetDeviationInPoints(30);
   g_trade.SetTypeFilling(ORDER_FILLING_IOC);

   // ATR indicator for trailing
   g_atr_handle = iATR(sym, PERIOD_H4, 14);
   if(g_atr_handle == INVALID_HANDLE)
     {
      Print("[DjibrilAI] Failed to create ATR indicator");
      return INIT_FAILED;
     }
   ArraySetAsSeries(g_atr_buffer, true);

   Print("[DjibrilAI] ══════════════════════════════════════");
   Print("[DjibrilAI] EA Initialized Successfully");
   Print("[DjibrilAI] Symbol: ", sym);
   Print("[DjibrilAI] Signal Dir: ", InpSignalDir);
   Print("[DjibrilAI] Magic: ", InpMagicNumber);
   Print("[DjibrilAI] ══════════════════════════════════════");

   return INIT_SUCCEEDED;
  }

//+------------------------------------------------------------------+
//| Expert deinitialization                                           |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   if(g_atr_handle != INVALID_HANDLE)
      IndicatorRelease(g_atr_handle);

   Comment("");
   Print("[DjibrilAI] EA Deinitialized. Reason: ", reason);
  }

//+------------------------------------------------------------------+
//| Expert tick function                                              |
//+------------------------------------------------------------------+
void OnTick()
  {
   // ── Drawdown circuit breaker ──
   if(!g_risk.CheckMaxDrawdown())
     {
      if(g_trading_enabled)
        {
         Print("[DjibrilAI] TRADING HALTED — Max drawdown exceeded");
         g_trading_enabled = false;
        }
      ManageOpenPositions();
      UpdatePanel("HALTED — MAX DD");
      return;
     }
   g_trading_enabled = true;

   // ── Session filter ──
   if(InpUseSessionFilter && !IsInSession())
     {
      ManageOpenPositions();  // Still manage existing trades
      UpdatePanel("Outside Session");
      return;
     }

   // ── Read signal ──
   OilSignal signal;
   if(!g_bridge.ReadLatestSignal(signal))
     {
      ManageOpenPositions();
      UpdatePanel("No Signal File");
      return;
     }

   // ── Freshness check ──
   if(!g_bridge.IsSignalFresh(signal))
     {
      ManageOpenPositions();
      UpdatePanel("Signal Expired");
      return;
     }

   // ── Duplicate check ──
   bool is_new_signal = (signal.signal_id != g_last_signal_id);

   // ── Process new signal ──
   if(is_new_signal && g_bridge.IsSignalActionable(signal))
     {
      ProcessSignal(signal);
      g_last_signal_id = signal.signal_id;
      g_last_signal = signal;
     }

   // ── Manage existing positions ──
   ManageOpenPositions();

   // ── Update panel ──
   UpdatePanel(signal.action + " | Conf: " + DoubleToString(signal.confidence * 100, 0) + "%");
  }

//+------------------------------------------------------------------+
//| Process a new trade signal                                        |
//+------------------------------------------------------------------+
void ProcessSignal(const OilSignal &signal)
  {
   string sym = _Symbol;

   Print("[DjibrilAI] ────────────────────────────────────");
   Print("[DjibrilAI] NEW SIGNAL: ", signal.signal_id);
   Print("[DjibrilAI] Action: ", signal.action, " | Conf: ",
         DoubleToString(signal.confidence * 100, 1), "%");
   Print("[DjibrilAI] Geo: ", signal.geo_score, " | Urgency: ", signal.urgency);

   // ── Pre-trade checks ──
   if(signal.confidence < InpMinConfidence)
     {
      Print("[DjibrilAI] Confidence too low: ", signal.confidence, " < ", InpMinConfidence);
      return;
     }

   if(!g_risk.CanOpenNewPosition(sym))
     {
      Print("[DjibrilAI] Risk manager rejected new position");
      return;
     }

   // ── Check for signal reversal (close opposing positions) ──
   if(signal.action == "BUY")
      ClosePositionsByType(sym, POSITION_TYPE_SELL, "Signal reversal to BUY");
   else if(signal.action == "SELL")
      ClosePositionsByType(sym, POSITION_TYPE_BUY, "Signal reversal to SELL");

   // ── Calculate lot size ──
   double sl_distance = MathAbs(signal.entry_price - signal.stop_loss);
   double lot_size = signal.lot_size;

   // Override with risk manager calculation if SL is valid
   if(sl_distance > 0)
     {
      double calc_lots = g_risk.CalculateLotSize(sym, sl_distance);
      if(calc_lots > 0)
         lot_size = MathMin(lot_size, calc_lots);  // Use the more conservative
     }

   lot_size = g_risk.NormalizeLot(sym, lot_size);

   if(lot_size <= 0)
     {
      Print("[DjibrilAI] Lot size is zero after normalization");
      return;
     }

   // ── Funds check ──
   ENUM_ORDER_TYPE order_type = (signal.action == "BUY") ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
   if(!g_risk.IsFundsAvailable(sym, lot_size, order_type))
     {
      Print("[DjibrilAI] Insufficient funds for ", lot_size, " lots");
      return;
     }

   // ── Execute trade ──
   double price = (signal.action == "BUY") ?
                  SymbolInfoDouble(sym, SYMBOL_ASK) :
                  SymbolInfoDouble(sym, SYMBOL_BID);

   double sl = NormalizeDouble(signal.stop_loss, _Digits);
   double tp = NormalizeDouble(signal.take_profit, _Digits);

   string comment = "DjibrilAI|" + signal.signal_id +
                    "|G" + IntegerToString(signal.geo_score) +
                    "|C" + DoubleToString(signal.confidence * 100, 0);

   bool result;
   if(signal.action == "BUY")
      result = g_trade.Buy(lot_size, sym, price, sl, tp, comment);
   else
      result = g_trade.Sell(lot_size, sym, price, sl, tp, comment);

   if(result)
     {
      Print("[DjibrilAI] ✓ Order executed: ", signal.action, " ", lot_size, " @ ", price);
      Print("[DjibrilAI]   SL: ", sl, " | TP: ", tp, " | R:R: ", signal.risk_reward);
     }
   else
     {
      Print("[DjibrilAI] ✗ Order FAILED: ", g_trade.ResultRetcode(),
            " - ", g_trade.ResultRetcodeDescription());

      // Handle requote / off-quotes with pending order
      if(g_trade.ResultRetcode() == TRADE_RETCODE_REQUOTE ||
         g_trade.ResultRetcode() == TRADE_RETCODE_PRICE_OFF)
        {
         Print("[DjibrilAI] Attempting limit order due to slippage...");
         if(signal.action == "BUY")
            g_trade.BuyLimit(lot_size, price - 5 * _Point, sym, sl, tp, ORDER_TIME_GTC, 0, comment);
         else
            g_trade.SellLimit(lot_size, price + 5 * _Point, sym, sl, tp, ORDER_TIME_GTC, 0, comment);
        }
     }
  }

//+------------------------------------------------------------------+
//| Manage open positions: trailing, breakeven, partial close         |
//+------------------------------------------------------------------+
void ManageOpenPositions()
  {
   if(CopyBuffer(g_atr_handle, 0, 0, 3, g_atr_buffer) < 3)
      return;

   double atr = g_atr_buffer[0];

   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;

      if(PositionGetInteger(POSITION_MAGIC) != InpMagicNumber)
         continue;

      if(PositionGetString(POSITION_SYMBOL) != _Symbol)
         continue;

      double open_price = PositionGetDouble(POSITION_PRICE_OPEN);
      double current_sl = PositionGetDouble(POSITION_SL);
      double current_tp = PositionGetDouble(POSITION_TP);
      double volume     = PositionGetDouble(POSITION_VOLUME);
      long   pos_type   = PositionGetInteger(POSITION_TYPE);
      double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
      double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);

      // ── Breakeven logic ──
      if(InpUseBreakeven)
        {
         double sl_distance = MathAbs(open_price - current_sl);
         if(pos_type == POSITION_TYPE_BUY && bid >= open_price + sl_distance)
           {
            if(current_sl < open_price)
              {
               double new_sl = open_price + 2 * _Point;
               g_trade.PositionModify(ticket, new_sl, current_tp);
               Print("[DjibrilAI] Breakeven set for BUY #", ticket);
              }
           }
         else if(pos_type == POSITION_TYPE_SELL && ask <= open_price - sl_distance)
           {
            if(current_sl > open_price || current_sl == 0)
              {
               double new_sl = open_price - 2 * _Point;
               g_trade.PositionModify(ticket, new_sl, current_tp);
               Print("[DjibrilAI] Breakeven set for SELL #", ticket);
              }
           }
        }

      // ── ATR Trailing Stop ──
      if(InpUseTrailing && atr > 0)
        {
         double trail_dist = atr * InpTrailATRMult;

         if(pos_type == POSITION_TYPE_BUY)
           {
            double new_sl = bid - trail_dist;
            new_sl = NormalizeDouble(new_sl, _Digits);
            if(new_sl > current_sl && new_sl > open_price)
              {
               g_trade.PositionModify(ticket, new_sl, current_tp);
              }
           }
         else if(pos_type == POSITION_TYPE_SELL)
           {
            double new_sl = ask + trail_dist;
            new_sl = NormalizeDouble(new_sl, _Digits);
            if((new_sl < current_sl || current_sl == 0) && new_sl < open_price)
              {
               g_trade.PositionModify(ticket, new_sl, current_tp);
              }
           }
        }

      // ── Partial close at intermediate target ──
      if(InpUsePartialClose && volume > SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN) * 2)
        {
         double tp_dist = MathAbs(current_tp - open_price);
         double intermediate = tp_dist * 0.5;  // 50% of TP distance

         bool hit_intermediate = false;
         if(pos_type == POSITION_TYPE_BUY && bid >= open_price + intermediate)
            hit_intermediate = true;
         if(pos_type == POSITION_TYPE_SELL && ask <= open_price - intermediate)
            hit_intermediate = true;

         if(hit_intermediate)
           {
            double close_vol = NormalizeDouble(volume * InpPartialPct, 2);
            double min_vol = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
            if(close_vol >= min_vol)
              {
               g_trade.PositionClosePartial(ticket, close_vol);
               Print("[DjibrilAI] Partial close ", close_vol, " lots on #", ticket);
              }
           }
        }
     }
  }

//+------------------------------------------------------------------+
//| Close positions by type (for signal reversal)                     |
//+------------------------------------------------------------------+
void ClosePositionsByType(const string symbol, ENUM_POSITION_TYPE type, string reason)
  {
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;

      if(PositionGetInteger(POSITION_MAGIC) != InpMagicNumber)
         continue;

      if(PositionGetString(POSITION_SYMBOL) != symbol)
         continue;

      if((ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE) == type)
        {
         g_trade.PositionClose(ticket);
         Print("[DjibrilAI] Closed #", ticket, " — ", reason);
        }
     }
  }

//+------------------------------------------------------------------+
//| Session filter                                                    |
//+------------------------------------------------------------------+
bool IsInSession()
  {
   MqlDateTime dt;
   TimeToStruct(TimeGMT(), dt);

   if(InpSessionStartH <= InpSessionEndH)
      return (dt.hour >= InpSessionStartH && dt.hour < InpSessionEndH);
   else
      return (dt.hour >= InpSessionStartH || dt.hour < InpSessionEndH);
  }

//+------------------------------------------------------------------+
//| Update chart comment / info panel                                 |
//+------------------------------------------------------------------+
void UpdatePanel(string status)
  {
   if(!InpShowPanel)
      return;

   double equity = g_risk.GetAccountEquity();
   double balance = g_risk.GetAccountBalance();
   double dd = g_risk.GetCurrentDrawdownPct();
   int positions = g_risk.CountOpenPositions(_Symbol);

   string text = "";
   text += "══════ Djibril AI v1.0 ══════\n";
   text += "Status:     " + status + "\n";
   text += "Balance:    $" + DoubleToString(balance, 2) + "\n";
   text += "Equity:     $" + DoubleToString(equity, 2) + "\n";
   text += "Drawdown:   " + DoubleToString(dd * 100, 2) + "%\n";
   text += "Positions:  " + IntegerToString(positions) + "/" + IntegerToString(InpMaxPositions) + "\n";

   if(g_last_signal.is_valid)
     {
      text += "───────────────────────────\n";
      text += "Signal:     " + g_last_signal.action + "\n";
      text += "Confidence: " + DoubleToString(g_last_signal.confidence * 100, 0) + "%\n";
      text += "Geo Score:  " + IntegerToString(g_last_signal.geo_score) + "/10\n";
      text += "Urgency:    " + g_last_signal.urgency + "\n";
      text += "ID:         " + g_last_signal.signal_id + "\n";
     }

   text += "══════════════════════════════";

   Comment(text);
  }
//+------------------------------------------------------------------+
