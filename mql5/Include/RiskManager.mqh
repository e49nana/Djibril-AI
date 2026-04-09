//+------------------------------------------------------------------+
//| RiskManager.mqh — Djibril AI Risk Management                       |
//| Position sizing, drawdown protection, spread/exposure validation.  |
//| Part of Djibril AI Trading System v1.0                             |
//+------------------------------------------------------------------+
#property copyright "Djibril AI / ExMachina Trading Systems"
#property link      "https://github.com/e49nana"
#property version   "1.00"
#property strict

#include <Trade\Trade.mqh>
#include <Trade\PositionInfo.mqh>
#include <Trade\AccountInfo.mqh>
#include <Trade\SymbolInfo.mqh>

//+------------------------------------------------------------------+
//| Risk Manager class                                                |
//+------------------------------------------------------------------+
class CRiskManager
  {
private:
   double            m_max_risk_pct;         // Max risk per trade (0.05 = 5%)
   double            m_max_drawdown_pct;     // Max account drawdown before stop (0.15 = 15%)
   int               m_max_spread_points;    // Max acceptable spread
   int               m_magic_number;         // EA magic number
   double            m_initial_balance;      // Balance at EA start
   int               m_max_open_positions;   // Max simultaneous positions

   CAccountInfo      m_account;
   CSymbolInfo       m_symbol;
   CPositionInfo     m_position;

public:
                     CRiskManager(void);
                    ~CRiskManager(void);

   // Configuration
   void              SetMaxRiskPct(double pct)       { m_max_risk_pct = pct; }
   void              SetMaxDrawdownPct(double pct)   { m_max_drawdown_pct = pct; }
   void              SetMaxSpread(int pts)            { m_max_spread_points = pts; }
   void              SetMagicNumber(int magic)        { m_magic_number = magic; }
   void              SetMaxPositions(int max)         { m_max_open_positions = max; }
   void              Initialize(const string symbol);

   // Lot size calculation
   double            CalculateLotSize(const string symbol, double sl_distance_price);
   double            CalculateLotSizeFromPips(const string symbol, double sl_pips);

   // Risk checks
   bool              CheckMaxDrawdown(void);
   bool              IsSpreadAcceptable(const string symbol);
   bool              IsFundsAvailable(const string symbol, double lot_size, ENUM_ORDER_TYPE order_type);
   double            GetCurrentExposure(const string symbol);
   int               CountOpenPositions(const string symbol);
   bool              CanOpenNewPosition(const string symbol);

   // Utility
   bool              IsNewBar(ENUM_TIMEFRAMES tf);
   double            GetAccountBalance(void);
   double            GetAccountEquity(void);
   double            GetCurrentDrawdownPct(void);
   double            NormalizeLot(const string symbol, double lot_size);
  };

//+------------------------------------------------------------------+
//| Constructor                                                       |
//+------------------------------------------------------------------+
CRiskManager::CRiskManager(void)
  {
   m_max_risk_pct       = 0.05;
   m_max_drawdown_pct   = 0.15;
   m_max_spread_points  = 50;
   m_magic_number       = 202503;
   m_max_open_positions = 3;
   m_initial_balance    = 0;
  }

//+------------------------------------------------------------------+
//| Destructor                                                        |
//+------------------------------------------------------------------+
CRiskManager::~CRiskManager(void)
  {
  }

//+------------------------------------------------------------------+
//| Initialize with current symbol                                    |
//+------------------------------------------------------------------+
void CRiskManager::Initialize(const string symbol)
  {
   m_symbol.Name(symbol);
   m_symbol.Refresh();
   m_initial_balance = m_account.Balance();
   Print("[RiskManager] Initialized | Balance: ", DoubleToString(m_initial_balance, 2),
         " | Symbol: ", symbol,
         " | MaxRisk: ", DoubleToString(m_max_risk_pct * 100, 1), "%",
         " | MaxDD: ", DoubleToString(m_max_drawdown_pct * 100, 1), "%");
  }

//+------------------------------------------------------------------+
//| Calculate lot size based on % risk and SL distance in price       |
//+------------------------------------------------------------------+
double CRiskManager::CalculateLotSize(const string symbol, double sl_distance_price)
  {
   if(sl_distance_price <= 0)
     {
      Print("[RiskManager] Invalid SL distance: ", sl_distance_price);
      return 0.0;
     }

   m_symbol.Name(symbol);
   m_symbol.Refresh();

   double balance      = m_account.Balance();
   double risk_amount  = balance * m_max_risk_pct;
   double tick_value   = m_symbol.TickValue();
   double tick_size    = m_symbol.TickSize();
   double point        = m_symbol.Point();

   if(tick_size <= 0 || tick_value <= 0)
     {
      Print("[RiskManager] Cannot get tick data for ", symbol);
      return 0.0;
     }

   // Calculate ticks in SL distance
   double sl_ticks = sl_distance_price / tick_size;

   // Risk per lot = ticks × tick_value
   double risk_per_lot = sl_ticks * tick_value;

   if(risk_per_lot <= 0)
     {
      Print("[RiskManager] Risk per lot is zero");
      return 0.0;
     }

   double raw_lots = risk_amount / risk_per_lot;
   return NormalizeLot(symbol, raw_lots);
  }

//+------------------------------------------------------------------+
//| Calculate lot size from SL in pips                                |
//+------------------------------------------------------------------+
double CRiskManager::CalculateLotSizeFromPips(const string symbol, double sl_pips)
  {
   m_symbol.Name(symbol);
   m_symbol.Refresh();

   double point = m_symbol.Point();
   if(point <= 0)
      return 0.0;

   double sl_price_distance = sl_pips * point;
   return CalculateLotSize(symbol, sl_price_distance);
  }

//+------------------------------------------------------------------+
//| Check if account drawdown exceeds maximum                         |
//+------------------------------------------------------------------+
bool CRiskManager::CheckMaxDrawdown(void)
  {
   double dd_pct = GetCurrentDrawdownPct();

   if(dd_pct >= m_max_drawdown_pct)
     {
      Print("[RiskManager] MAX DRAWDOWN REACHED: ",
            DoubleToString(dd_pct * 100, 2), "% >= ",
            DoubleToString(m_max_drawdown_pct * 100, 1), "%");
      return false;  // NOT OK to trade
     }

   return true;  // OK to trade
  }

//+------------------------------------------------------------------+
//| Get current drawdown as fraction                                  |
//+------------------------------------------------------------------+
double CRiskManager::GetCurrentDrawdownPct(void)
  {
   if(m_initial_balance <= 0)
      m_initial_balance = m_account.Balance();

   double equity = m_account.Equity();
   double peak   = MathMax(m_initial_balance, m_account.Balance());

   if(peak <= 0)
      return 0.0;

   return (peak - equity) / peak;
  }

//+------------------------------------------------------------------+
//| Check if current spread is acceptable                             |
//+------------------------------------------------------------------+
bool CRiskManager::IsSpreadAcceptable(const string symbol)
  {
   m_symbol.Name(symbol);
   m_symbol.Refresh();

   int spread = m_symbol.Spread();

   if(spread > m_max_spread_points)
     {
      Print("[RiskManager] Spread too high: ", spread, " > ", m_max_spread_points);
      return false;
     }

   return true;
  }

//+------------------------------------------------------------------+
//| Check if sufficient funds are available for a trade               |
//+------------------------------------------------------------------+
bool CRiskManager::IsFundsAvailable(const string symbol, double lot_size, ENUM_ORDER_TYPE order_type)
  {
   double margin_required = 0;
   if(!OrderCalcMargin(order_type, symbol, lot_size, SymbolInfoDouble(symbol, SYMBOL_ASK), margin_required))
     {
      Print("[RiskManager] Cannot calculate margin requirement");
      return false;
     }

   double free_margin = m_account.FreeMargin();

   if(margin_required > free_margin * 0.8)  // Keep 20% buffer
     {
      Print("[RiskManager] Insufficient margin: need ",
            DoubleToString(margin_required, 2),
            " but only ", DoubleToString(free_margin, 2), " available");
      return false;
     }

   return true;
  }

//+------------------------------------------------------------------+
//| Get total exposure on a symbol (sum of lot sizes)                 |
//+------------------------------------------------------------------+
double CRiskManager::GetCurrentExposure(const string symbol)
  {
   double total_lots = 0;

   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      if(m_position.SelectByIndex(i))
        {
         if(m_position.Symbol() == symbol && m_position.Magic() == m_magic_number)
           {
            total_lots += m_position.Volume();
           }
        }
     }

   return total_lots;
  }

//+------------------------------------------------------------------+
//| Count open positions for this EA on a symbol                      |
//+------------------------------------------------------------------+
int CRiskManager::CountOpenPositions(const string symbol)
  {
   int count = 0;

   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      if(m_position.SelectByIndex(i))
        {
         if(m_position.Symbol() == symbol && m_position.Magic() == m_magic_number)
           {
            count++;
           }
        }
     }

   return count;
  }

//+------------------------------------------------------------------+
//| Check if we can open a new position                               |
//+------------------------------------------------------------------+
bool CRiskManager::CanOpenNewPosition(const string symbol)
  {
   if(!CheckMaxDrawdown())
      return false;

   if(!IsSpreadAcceptable(symbol))
      return false;

   if(CountOpenPositions(symbol) >= m_max_open_positions)
     {
      Print("[RiskManager] Max positions reached: ", m_max_open_positions);
      return false;
     }

   return true;
  }

//+------------------------------------------------------------------+
//| Detect new bar on the given timeframe                             |
//+------------------------------------------------------------------+
bool CRiskManager::IsNewBar(ENUM_TIMEFRAMES tf)
  {
   static datetime last_bar_time = 0;
   datetime current_bar = iTime(_Symbol, tf, 0);

   if(current_bar != last_bar_time)
     {
      last_bar_time = current_bar;
      return true;
     }

   return false;
  }

//+------------------------------------------------------------------+
//| Getters                                                           |
//+------------------------------------------------------------------+
double CRiskManager::GetAccountBalance(void)
  {
   return m_account.Balance();
  }

double CRiskManager::GetAccountEquity(void)
  {
   return m_account.Equity();
  }

//+------------------------------------------------------------------+
//| Normalize lot size to broker constraints                          |
//+------------------------------------------------------------------+
double CRiskManager::NormalizeLot(const string symbol, double lot_size)
  {
   m_symbol.Name(symbol);
   m_symbol.Refresh();

   double min_lot  = m_symbol.LotsMin();
   double max_lot  = m_symbol.LotsMax();
   double lot_step = m_symbol.LotsStep();

   if(lot_step <= 0)
      lot_step = 0.01;

   // Round to nearest lot step
   lot_size = MathFloor(lot_size / lot_step) * lot_step;

   // Clamp to min/max
   lot_size = MathMax(min_lot, lot_size);
   lot_size = MathMin(max_lot, lot_size);

   return NormalizeDouble(lot_size, 2);
  }
//+------------------------------------------------------------------+
