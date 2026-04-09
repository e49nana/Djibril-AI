//+------------------------------------------------------------------+
//| DjibrilAI_Backtest.mq5 — Historical Signal Replay                  |
//| Reads historical signals from CSV, simulates entries/exits,        |
//| and generates a performance report.                                |
//+------------------------------------------------------------------+
#property copyright "Djibril AI / ExMachina Trading Systems"
#property link      "https://github.com/e49nana"
#property version   "1.00"
#property description "Backtesting harness for Djibril AI signals"
#property strict

#include "Include\\RiskManager.mqh"
#include <Trade\Trade.mqh>

//+------------------------------------------------------------------+
//| Input Parameters                                                  |
//+------------------------------------------------------------------+
input string   InpCSVFile          = "djibril_signals_history.csv";  // CSV file path
input int      InpMagicNumber      = 202599;           // Backtest magic number
input double   InpMaxRiskPct       = 0.05;             // Max risk per trade
input double   InpSlippagePts      = 10;               // Simulated slippage (points)
input double   InpSpreadPts        = 30;               // Simulated spread (points)
input bool     InpUseTrailing      = true;             // Enable trailing stop
input double   InpTrailATRMult     = 0.8;              // Trailing ATR multiplier

//+------------------------------------------------------------------+
//| Signal record from CSV                                            |
//+------------------------------------------------------------------+
struct CSVSignal
  {
   datetime          time;
   string            action;       // BUY, SELL, FLAT
   double            entry_price;
   double            stop_loss;
   double            take_profit;
   double            confidence;
   int               geo_score;
   double            lot_size;
  };

//+------------------------------------------------------------------+
//| Performance tracker                                               |
//+------------------------------------------------------------------+
struct BacktestStats
  {
   int               total_trades;
   int               winners;
   int               losers;
   double            gross_profit;
   double            gross_loss;
   double            max_drawdown;
   double            peak_equity;
   double            total_pnl;
  };

//+------------------------------------------------------------------+
//| Globals                                                           |
//+------------------------------------------------------------------+
CTrade         g_trade;
CRiskManager   g_risk;
CSVSignal      g_signals[];
int            g_signal_count = 0;
int            g_signal_index = 0;
BacktestStats  g_stats;
int            g_atr_handle = INVALID_HANDLE;
double         g_atr_buffer[];

//+------------------------------------------------------------------+
//| Expert initialization                                             |
//+------------------------------------------------------------------+
int OnInit()
  {
   // Init trade
   g_trade.SetExpertMagicNumber(InpMagicNumber);
   g_trade.SetDeviationInPoints((ulong)InpSlippagePts);

   // Init risk manager
   g_risk.SetMagicNumber(InpMagicNumber);
   g_risk.SetMaxRiskPct(InpMaxRiskPct);
   g_risk.Initialize(_Symbol);

   // ATR
   g_atr_handle = iATR(_Symbol, PERIOD_H4, 14);
   if(g_atr_handle == INVALID_HANDLE)
     {
      Print("[Backtest] ATR indicator failed");
      return INIT_FAILED;
     }
   ArraySetAsSeries(g_atr_buffer, true);

   // Load CSV signals
   if(!LoadCSVSignals())
     {
      Print("[Backtest] Failed to load CSV signals. Creating sample file...");
      CreateSampleCSV();
      if(!LoadCSVSignals())
         return INIT_FAILED;
     }

   // Init stats
   ZeroMemory(g_stats);
   g_stats.peak_equity = AccountInfoDouble(ACCOUNT_EQUITY);

   g_signal_index = 0;

   Print("[Backtest] ══════════════════════════════════════");
   Print("[Backtest] Loaded ", g_signal_count, " signals from CSV");
   Print("[Backtest] Starting equity: ", g_stats.peak_equity);
   Print("[Backtest] ══════════════════════════════════════");

   return INIT_SUCCEEDED;
  }

//+------------------------------------------------------------------+
//| Expert deinitialization                                           |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   if(g_atr_handle != INVALID_HANDLE)
      IndicatorRelease(g_atr_handle);

   PrintReport();
  }

//+------------------------------------------------------------------+
//| Expert tick function                                              |
//+------------------------------------------------------------------+
void OnTick()
  {
   if(g_signal_index >= g_signal_count)
      return;

   datetime current_time = TimeCurrent();

   // Check if it's time for the next signal
   while(g_signal_index < g_signal_count &&
         g_signals[g_signal_index].time <= current_time)
     {
      ProcessBacktestSignal(g_signals[g_signal_index]);
      g_signal_index++;
     }

   // Track drawdown
   double equity = AccountInfoDouble(ACCOUNT_EQUITY);
   if(equity > g_stats.peak_equity)
      g_stats.peak_equity = equity;

   double dd = (g_stats.peak_equity - equity) / g_stats.peak_equity;
   if(dd > g_stats.max_drawdown)
      g_stats.max_drawdown = dd;
  }

//+------------------------------------------------------------------+
//| Process a single backtest signal                                  |
//+------------------------------------------------------------------+
void ProcessBacktestSignal(const CSVSignal &signal)
  {
   if(signal.action == "FLAT" || signal.action == "")
      return;

   if(signal.confidence < 0.5)
      return;

   string sym = _Symbol;
   double lot = signal.lot_size;
   if(lot <= 0)
      lot = 0.01;
   lot = g_risk.NormalizeLot(sym, lot);

   // Add simulated slippage
   double slip = InpSlippagePts * SymbolInfoDouble(sym, SYMBOL_POINT);

   double sl = signal.stop_loss;
   double tp = signal.take_profit;

   bool result;
   if(signal.action == "BUY")
     {
      double price = SymbolInfoDouble(sym, SYMBOL_ASK) + slip;
      result = g_trade.Buy(lot, sym, price, sl, tp, "BT|G" + IntegerToString(signal.geo_score));
     }
   else if(signal.action == "SELL")
     {
      double price = SymbolInfoDouble(sym, SYMBOL_BID) - slip;
      result = g_trade.Sell(lot, sym, price, sl, tp, "BT|G" + IntegerToString(signal.geo_score));
     }
   else
      return;

   if(result)
      Print("[Backtest] Signal executed: ", signal.action, " ", lot, " lots");
  }

//+------------------------------------------------------------------+
//| OnTrade — track completed trades                                  |
//+------------------------------------------------------------------+
void OnTrade()
  {
   // Count from history deals
   if(HistorySelect(0, TimeCurrent()))
     {
      int total = HistoryDealsTotal();
      for(int i = total - 1; i >= MathMax(0, total - 5); i--)
        {
         ulong ticket = HistoryDealGetTicket(i);
         if(ticket == 0)
            continue;

         if(HistoryDealGetInteger(ticket, DEAL_MAGIC) != InpMagicNumber)
            continue;

         long deal_type = HistoryDealGetInteger(ticket, DEAL_ENTRY);
         if(deal_type == DEAL_ENTRY_OUT || deal_type == DEAL_ENTRY_OUT_BY)
           {
            double profit = HistoryDealGetDouble(ticket, DEAL_PROFIT);
            g_stats.total_trades++;
            g_stats.total_pnl += profit;

            if(profit > 0)
              {
               g_stats.winners++;
               g_stats.gross_profit += profit;
              }
            else
              {
               g_stats.losers++;
               g_stats.gross_loss += MathAbs(profit);
              }
           }
        }
     }
  }

//+------------------------------------------------------------------+
//| Print final performance report                                    |
//+------------------------------------------------------------------+
void PrintReport()
  {
   double win_rate = (g_stats.total_trades > 0) ?
                     (double)g_stats.winners / g_stats.total_trades * 100 : 0;
   double profit_factor = (g_stats.gross_loss > 0) ?
                          g_stats.gross_profit / g_stats.gross_loss : 0;

   // Sharpe ratio approximation (simplified)
   double avg_return = (g_stats.total_trades > 0) ?
                       g_stats.total_pnl / g_stats.total_trades : 0;

   Print("══════════════════════════════════════════════");
   Print("     Djibril AI BACKTEST REPORT                ");
   Print("══════════════════════════════════════════════");
   Print("Total Trades:    ", g_stats.total_trades);
   Print("Winners:         ", g_stats.winners);
   Print("Losers:          ", g_stats.losers);
   Print("Win Rate:        ", DoubleToString(win_rate, 1), "%");
   Print("Gross Profit:    $", DoubleToString(g_stats.gross_profit, 2));
   Print("Gross Loss:      $", DoubleToString(g_stats.gross_loss, 2));
   Print("Net P&L:         $", DoubleToString(g_stats.total_pnl, 2));
   Print("Profit Factor:   ", DoubleToString(profit_factor, 2));
   Print("Max Drawdown:    ", DoubleToString(g_stats.max_drawdown * 100, 2), "%");
   Print("Avg Trade:       $", DoubleToString(avg_return, 2));
   Print("══════════════════════════════════════════════");
  }

//+------------------------------------------------------------------+
//| Load signals from CSV file                                        |
//+------------------------------------------------------------------+
bool LoadCSVSignals()
  {
   int handle = FileOpen(InpCSVFile, FILE_READ | FILE_CSV | FILE_ANSI | FILE_COMMON, ',');
   if(handle == INVALID_HANDLE)
     {
      handle = FileOpen(InpCSVFile, FILE_READ | FILE_CSV | FILE_ANSI, ',');
      if(handle == INVALID_HANDLE)
         return false;
     }

   // Skip header
   if(!FileIsEnding(handle))
     {
      FileReadString(handle); FileReadString(handle); FileReadString(handle);
      FileReadString(handle); FileReadString(handle); FileReadString(handle);
      FileReadString(handle); FileReadString(handle);
     }

   g_signal_count = 0;
   ArrayResize(g_signals, 0);

   while(!FileIsEnding(handle))
     {
      CSVSignal sig;

      string time_str = FileReadString(handle);
      sig.action      = FileReadString(handle);
      string entry_s  = FileReadString(handle);
      string sl_s     = FileReadString(handle);
      string tp_s     = FileReadString(handle);
      string conf_s   = FileReadString(handle);
      string geo_s    = FileReadString(handle);
      string lot_s    = FileReadString(handle);

      if(time_str == "" || sig.action == "")
         continue;

      sig.time        = StringToTime(time_str);
      sig.entry_price = StringToDouble(entry_s);
      sig.stop_loss   = StringToDouble(sl_s);
      sig.take_profit = StringToDouble(tp_s);
      sig.confidence  = StringToDouble(conf_s);
      sig.geo_score   = (int)StringToInteger(geo_s);
      sig.lot_size    = StringToDouble(lot_s);

      g_signal_count++;
      ArrayResize(g_signals, g_signal_count);
      g_signals[g_signal_count - 1] = sig;
     }

   FileClose(handle);
   return (g_signal_count > 0);
  }

//+------------------------------------------------------------------+
//| Create a sample CSV for testing                                   |
//+------------------------------------------------------------------+
void CreateSampleCSV()
  {
   int handle = FileOpen(InpCSVFile, FILE_WRITE | FILE_CSV | FILE_ANSI | FILE_COMMON, ',');
   if(handle == INVALID_HANDLE)
      return;

   // Header
   FileWrite(handle, "time", "action", "entry_price", "stop_loss",
             "take_profit", "confidence", "geo_score", "lot_size");

   // Sample signals
   FileWrite(handle, "2025.01.15 10:00", "BUY", "75.50", "74.00", "78.00", "0.82", "7", "0.10");
   FileWrite(handle, "2025.01.20 14:00", "SELL", "78.20", "79.50", "76.00", "0.75", "-5", "0.08");
   FileWrite(handle, "2025.02.01 09:00", "BUY", "72.00", "70.50", "75.00", "0.90", "8", "0.12");
   FileWrite(handle, "2025.02.10 16:00", "FLAT", "0", "0", "0", "0.40", "2", "0");
   FileWrite(handle, "2025.02.20 11:00", "SELL", "76.80", "78.30", "74.00", "0.70", "-4", "0.07");

   FileClose(handle);
   Print("[Backtest] Created sample CSV with 5 signals");
  }
//+------------------------------------------------------------------+
