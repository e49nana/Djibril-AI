//+------------------------------------------------------------------+
//| SignalBridge.mqh — Djibril AI Signal Reader                        |
//| Reads and parses JSON trade signals from the Python backend.      |
//| Part of Djibril AI Trading System v1.0                             |
//+------------------------------------------------------------------+
#property copyright "Djibril AI / ExMachina Trading Systems"
#property link      "https://github.com/e49nana"
#property version   "1.00"
#property strict

//+------------------------------------------------------------------+
//| Signal data structure                                             |
//+------------------------------------------------------------------+
struct OilSignal
  {
   string            signal_id;
   string            action;        // "BUY", "SELL", "FLAT"
   string            symbol;
   double            confidence;
   double            entry_price;
   double            stop_loss;
   double            take_profit;
   double            lot_size;
   double            kelly_fraction;
   double            sl_pips;
   double            tp_pips;
   double            risk_reward;
   int               max_spread;
   string            reasoning;
   int               geo_score;
   double            tech_score;
   double            sent_score;
   string            urgency;       // "low","medium","high","critical"
   datetime          created_at;
   datetime          expires_at;
   bool              is_valid;
   string            error_msg;
  };

//+------------------------------------------------------------------+
//| SignalBridge class                                                 |
//+------------------------------------------------------------------+
class CSignalBridge
  {
private:
   string            m_signal_dir;
   string            m_signal_file;
   int               m_max_age_sec;

   // JSON parsing helpers
   string            ExtractJsonString(const string &json, const string &key);
   double            ExtractJsonDouble(const string &json, const string &key);
   int               ExtractJsonInt(const string &json, const string &key);
   datetime          ParseISO8601(const string &iso_str);
   string            TrimQuotes(const string &s);

public:
                     CSignalBridge(void);
                    ~CSignalBridge(void);

   // Configuration
   void              SetSignalDir(const string dir)   { m_signal_dir = dir; }
   void              SetMaxAgeSec(const int sec)       { m_max_age_sec = sec; }

   // Core methods
   bool              ReadLatestSignal(OilSignal &signal);
   bool              IsSignalFresh(const OilSignal &signal);
   bool              IsSignalActionable(const OilSignal &signal);
   string            GetSignalDir(void) { return m_signal_dir; }
  };

//+------------------------------------------------------------------+
//| Constructor                                                       |
//+------------------------------------------------------------------+
CSignalBridge::CSignalBridge(void)
  {
   m_signal_dir  = "signals";
   m_signal_file = "latest_signal.json";
   m_max_age_sec = 300;  // 5 minutes
  }

//+------------------------------------------------------------------+
//| Destructor                                                        |
//+------------------------------------------------------------------+
CSignalBridge::~CSignalBridge(void)
  {
  }

//+------------------------------------------------------------------+
//| Read and parse the latest signal JSON file                        |
//+------------------------------------------------------------------+
bool CSignalBridge::ReadLatestSignal(OilSignal &signal)
  {
   // Initialize signal
   signal.is_valid  = false;
   signal.error_msg = "";

   string filepath = m_signal_dir + "\\" + m_signal_file;

   // Check file exists
   if(!FileIsExist(filepath, FILE_COMMON))
     {
      // Try without common flag
      if(!FileIsExist(filepath, 0))
        {
         signal.error_msg = "Signal file not found: " + filepath;
         return false;
        }
     }

   // Open file
   int handle = FileOpen(filepath, FILE_READ | FILE_TXT | FILE_ANSI | FILE_COMMON);
   if(handle == INVALID_HANDLE)
     {
      handle = FileOpen(filepath, FILE_READ | FILE_TXT | FILE_ANSI);
      if(handle == INVALID_HANDLE)
        {
         signal.error_msg = "Cannot open signal file: " + IntegerToString(GetLastError());
         return false;
        }
     }

   // Read entire file content
   string json = "";
   while(!FileIsEnding(handle))
     {
      json += FileReadString(handle) + " ";
     }
   FileClose(handle);

   if(StringLen(json) < 10)
     {
      signal.error_msg = "Signal file is empty or too short";
      return false;
     }

   // Parse JSON fields
   signal.signal_id    = ExtractJsonString(json, "signal_id");
   signal.action       = ExtractJsonString(json, "action");
   signal.symbol       = ExtractJsonString(json, "symbol");
   signal.confidence   = ExtractJsonDouble(json, "confidence");
   signal.entry_price  = ExtractJsonDouble(json, "entry_price");
   signal.stop_loss    = ExtractJsonDouble(json, "stop_loss");
   signal.take_profit  = ExtractJsonDouble(json, "take_profit");
   signal.lot_size     = ExtractJsonDouble(json, "lot_size");
   signal.kelly_fraction = ExtractJsonDouble(json, "kelly_fraction");
   signal.sl_pips      = ExtractJsonDouble(json, "sl_pips");
   signal.tp_pips      = ExtractJsonDouble(json, "tp_pips");
   signal.risk_reward  = ExtractJsonDouble(json, "risk_reward_ratio");
   signal.max_spread   = ExtractJsonInt(json, "max_spread_allowed");
   signal.reasoning    = ExtractJsonString(json, "reasoning");
   signal.geo_score    = ExtractJsonInt(json, "geo_score");
   signal.tech_score   = ExtractJsonDouble(json, "technical_score_value");
   signal.sent_score   = ExtractJsonDouble(json, "sentiment_score_value");
   signal.urgency      = ExtractJsonString(json, "urgency");

   // Parse timestamps
   string created_str  = ExtractJsonString(json, "created_at");
   string expires_str  = ExtractJsonString(json, "expires_at");
   signal.created_at   = ParseISO8601(created_str);
   signal.expires_at   = ParseISO8601(expires_str);

   // Validate minimum required fields
   if(signal.action == "" || signal.signal_id == "")
     {
      signal.error_msg = "Missing required fields (action or signal_id)";
      return false;
     }

   signal.is_valid = true;
   return true;
  }

//+------------------------------------------------------------------+
//| Check if signal is still fresh (not expired)                      |
//+------------------------------------------------------------------+
bool CSignalBridge::IsSignalFresh(const OilSignal &signal)
  {
   if(!signal.is_valid)
      return false;

   datetime now = TimeCurrent();

   // Check max age
   if(signal.created_at > 0 && (now - signal.created_at) > m_max_age_sec)
      return false;

   // Check expiration
   if(signal.expires_at > 0 && now > signal.expires_at)
      return false;

   return true;
  }

//+------------------------------------------------------------------+
//| Check if signal is actionable (BUY or SELL with valid params)     |
//+------------------------------------------------------------------+
bool CSignalBridge::IsSignalActionable(const OilSignal &signal)
  {
   if(!signal.is_valid)
      return false;

   if(signal.action != "BUY" && signal.action != "SELL")
      return false;

   if(signal.entry_price <= 0 || signal.stop_loss <= 0 || signal.take_profit <= 0)
      return false;

   if(signal.lot_size <= 0)
      return false;

   if(signal.confidence < 0.3)
      return false;

   return true;
  }

//+------------------------------------------------------------------+
//| Extract a string value from JSON by key                           |
//+------------------------------------------------------------------+
string CSignalBridge::ExtractJsonString(const string &json, const string &key)
  {
   string search = "\"" + key + "\"";
   int pos = StringFind(json, search);
   if(pos < 0)
      return "";

   // Find the colon after the key
   int colon = StringFind(json, ":", pos + StringLen(search));
   if(colon < 0)
      return "";

   // Skip whitespace after colon
   int start = colon + 1;
   while(start < StringLen(json) && StringGetCharacter(json, start) == ' ')
      start++;

   // Check if value is a string (starts with quote)
   if(StringGetCharacter(json, start) == '"')
     {
      start++;
      int end = StringFind(json, "\"", start);
      if(end < 0)
         return "";
      return StringSubstr(json, start, end - start);
     }

   // Value is not a string — return raw until comma/brace
   int end = start;
   while(end < StringLen(json))
     {
      ushort ch = StringGetCharacter(json, end);
      if(ch == ',' || ch == '}' || ch == ']' || ch == '\n')
         break;
      end++;
     }

   string val = StringSubstr(json, start, end - start);
   StringTrimLeft(val);
   StringTrimRight(val);
   return val;
  }

//+------------------------------------------------------------------+
//| Extract a double value from JSON by key                           |
//+------------------------------------------------------------------+
double CSignalBridge::ExtractJsonDouble(const string &json, const string &key)
  {
   string val = ExtractJsonString(json, key);
   if(val == "" || val == "null")
      return 0.0;
   return StringToDouble(val);
  }

//+------------------------------------------------------------------+
//| Extract an int value from JSON by key                             |
//+------------------------------------------------------------------+
int CSignalBridge::ExtractJsonInt(const string &json, const string &key)
  {
   string val = ExtractJsonString(json, key);
   if(val == "" || val == "null")
      return 0;
   return (int)StringToInteger(val);
  }

//+------------------------------------------------------------------+
//| Parse ISO 8601 datetime string to MQL5 datetime                   |
//+------------------------------------------------------------------+
datetime CSignalBridge::ParseISO8601(const string &iso_str)
  {
   if(StringLen(iso_str) < 19)
      return 0;

   // Format: 2025-03-14T20:30:00+00:00 or 2025-03-14T20:30:00.123456+00:00
   string date_part = StringSubstr(iso_str, 0, 10);   // 2025-03-14
   string time_part = StringSubstr(iso_str, 11, 8);    // 20:30:00

   // Replace dashes and colons for StrToTime compatibility
   StringReplace(date_part, "-", ".");

   string combined = date_part + " " + time_part;
   return StringToTime(combined);
  }

//+------------------------------------------------------------------+
//| Trim surrounding quotes from a string                             |
//+------------------------------------------------------------------+
string CSignalBridge::TrimQuotes(const string &s)
  {
   string result = s;
   StringTrimLeft(result);
   StringTrimRight(result);
   if(StringLen(result) >= 2)
     {
      if(StringGetCharacter(result, 0) == '"' &&
         StringGetCharacter(result, StringLen(result)-1) == '"')
        {
         result = StringSubstr(result, 1, StringLen(result) - 2);
        }
     }
   return result;
  }
//+------------------------------------------------------------------+
