//+------------------------------------------------------------------+
//|                                    OrionTrader.mq5               |
//|                     Orion — Data Collector + Trade Executor       |
//|  Collecte les données OHLCV sur 5 TF, envoie à Orion,           |
//|  reçoit les ordres et les exécute sur MT5.                       |
//+------------------------------------------------------------------+
#property copyright "Orion Trading System"
#property version   "2.0"
#property strict

#include <Trade\Trade.mqh>
#include <Trade\PositionInfo.mqh>

//--- Paramètres
input string   OrionURL        = "http://127.0.0.1:8765";  // URL du serveur Orion
input string   OrionToken      = "orion_secret_change_me"; // Token secret
input string   Symbol_         = "XAUUSDm";                 // Symbole à trader
input double   RiskPercent     = 1.0;                       // Risque par trade (%)
input int      MagicNumber     = 20250101;                  // Magic number
input int      DataInterval    = 15;                        // Intervalle envoi données (secondes)
input bool     AutoTrade       = true;                      // Trading automatique activé

//--- Objets
CTrade         trade;
CPositionInfo  posInfo;

//--- Timers
datetime lastDataSend  = 0;
datetime lastCmdCheck  = 0;
int      httpTimeout   = 5000;

//+------------------------------------------------------------------+
//| Expert initialization                                             |
//+------------------------------------------------------------------+
int OnInit() {
   trade.SetExpertMagicNumber(MagicNumber);
   trade.SetDeviationInPoints(20);
   trade.SetTypeFilling(ORDER_FILLING_IOC);
   EventSetTimer(1);
   Print("[ORION] EA initialisé — Symbole: ", Symbol_, " | URL: ", OrionURL);
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason) {
   EventKillTimer();
   Print("[ORION] EA arrêté.");
}

//+------------------------------------------------------------------+
//| Timer — cœur du système                                          |
//+------------------------------------------------------------------+
void OnTimer() {
   datetime now = TimeCurrent();

   // Envoi données marché toutes les N secondes
   if (now - lastDataSend >= DataInterval) {
      SendMarketData();
      lastDataSend = now;
   }

   // Vérification commandes Orion toutes les 3 secondes
   if (AutoTrade && now - lastCmdCheck >= 3) {
      CheckAndExecuteCommands();
      lastCmdCheck = now;
   }
}

//+------------------------------------------------------------------+
//| Construction et envoi des données marché                         |
//+------------------------------------------------------------------+
void SendMarketData() {
   string json = BuildMarketDataJSON();
   string response = "";
   int res = HTTPSend("/api/market-data", json, response);
   if (res == 200)
      Print("[ORION] Données envoyées OK");
   else
      Print("[ORION] Erreur envoi données: ", res);
}

string BuildMarketDataJSON() {
   ENUM_TIMEFRAMES tfs[5] = {PERIOD_M5, PERIOD_M15, PERIOD_M30, PERIOD_H1, PERIOD_H4};
   string tfNames[5]      = {"M5","M15","M30","H1","H4"};
   int    barsCount[5]    = {50, 30, 20, 20, 15};

   string json = "{";
   json += "\"symbol\":\"" + Symbol_ + "\",";
   json += "\"timestamp\":" + (string)(long)TimeCurrent() + ",";
   json += "\"spread\":" + (string)SymbolInfoInteger(Symbol_, SYMBOL_SPREAD) + ",";
   json += "\"bid\":" + DoubleToString(SymbolInfoDouble(Symbol_, SYMBOL_BID), 5) + ",";
   json += "\"ask\":" + DoubleToString(SymbolInfoDouble(Symbol_, SYMBOL_ASK), 5) + ",";

   // Positions ouvertes
   json += "\"open_positions\":" + GetOpenPositionsJSON() + ",";

   // Account info
   json += "\"account\":{";
   json += "\"balance\":" + DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE), 2) + ",";
   json += "\"equity\":" + DoubleToString(AccountInfoDouble(ACCOUNT_EQUITY), 2) + ",";
   json += "\"margin_free\":" + DoubleToString(AccountInfoDouble(ACCOUNT_MARGIN_FREE), 2);
   json += "},";

   // Données multi-timeframe
   json += "\"timeframes\":{";
   for (int t = 0; t < 5; t++) {
      int bars = barsCount[t];
      json += "\"" + tfNames[t] + "\":{";

      // OHLCV
      json += "\"candles\":[";
      MqlRates rates[];
      int copied = CopyRates(Symbol_, tfs[t], 0, bars, rates);
      if (copied > 0) {
         for (int i = copied - 1; i >= 0; i--) {
            if (i < copied - 1) json += ",";
            json += "{";
            json += "\"t\":" + (string)(long)rates[i].time + ",";
            json += "\"o\":" + DoubleToString(rates[i].open, 5) + ",";
            json += "\"h\":" + DoubleToString(rates[i].high, 5) + ",";
            json += "\"l\":" + DoubleToString(rates[i].low, 5) + ",";
            json += "\"c\":" + DoubleToString(rates[i].close, 5) + ",";
            json += "\"v\":" + (string)rates[i].tick_volume;
            json += "}";
         }
      }
      json += "],";

      // ATR 14
      double atrBuf[];
      int atrHandle = iATR(Symbol_, tfs[t], 14);
      double atr = 0;
      if (atrHandle != INVALID_HANDLE && CopyBuffer(atrHandle, 0, 0, 1, atrBuf) > 0)
         atr = atrBuf[0];
      json += "\"atr\":" + DoubleToString(atr, 5) + ",";

      // Swing highs/lows (20 bougies)
      double swingHigh = 0, swingLow = 999999;
      MqlRates swingRates[];
      if (CopyRates(Symbol_, tfs[t], 0, 20, swingRates) > 0) {
         for (int i = 0; i < 20; i++) {
            if (swingRates[i].high > swingHigh) swingHigh = swingRates[i].high;
            if (swingRates[i].low < swingLow)   swingLow  = swingRates[i].low;
         }
      }
      json += "\"swing_high\":" + DoubleToString(swingHigh, 5) + ",";
      json += "\"swing_low\":" + DoubleToString(swingLow, 5);

      json += "}";
      if (t < 4) json += ",";
   }
   json += "}"; // timeframes
   json += "}"; // root
   return json;
}

string GetOpenPositionsJSON() {
   string arr = "[";
   int total = PositionsTotal();
   int count = 0;
   for (int i = 0; i < total; i++) {
      if (posInfo.SelectByIndex(i) && posInfo.Magic() == MagicNumber) {
         if (count > 0) arr += ",";
         arr += "{";
         arr += "\"ticket\":" + (string)posInfo.Ticket() + ",";
         arr += "\"type\":\"" + (posInfo.PositionType() == POSITION_TYPE_BUY ? "BUY" : "SELL") + "\",";
         arr += "\"volume\":" + DoubleToString(posInfo.Volume(), 2) + ",";
         arr += "\"open_price\":" + DoubleToString(posInfo.PriceOpen(), 5) + ",";
         arr += "\"sl\":" + DoubleToString(posInfo.StopLoss(), 5) + ",";
         arr += "\"tp\":" + DoubleToString(posInfo.TakeProfit(), 5) + ",";
         arr += "\"profit\":" + DoubleToString(posInfo.Profit(), 2);
         arr += "}";
         count++;
      }
   }
   return arr + "]";
}

//+------------------------------------------------------------------+
//| Vérification et exécution des commandes Orion                    |
//+------------------------------------------------------------------+
void CheckAndExecuteCommands() {
   string response = "";
   int res = HTTPGet("/api/trade-command?magic=" + (string)MagicNumber, response);
   if (res != 200 || StringLen(response) < 5) return;

   // Parse simple JSON (sans lib externe)
   string action = ExtractJSONString(response, "action");
   if (action == "none" || action == "") return;

   Print("[ORION] Commande reçue: ", response);

   if (action == "BUY" || action == "SELL") {
      double entry    = ExtractJSONDouble(response, "entry");
      double sl       = ExtractJSONDouble(response, "sl");
      double tp       = ExtractJSONDouble(response, "tp");
      double lot      = ExtractJSONDouble(response, "lot");
      string comment  = ExtractJSONString(response, "comment");

      if (lot <= 0) lot = CalculateLotSize(sl);

      bool ok = false;
      if (action == "BUY")
         ok = trade.Buy(lot, Symbol_, 0, sl, tp, comment);
      else
         ok = trade.Sell(lot, Symbol_, 0, sl, tp, comment);

      if (ok)
         Print("[ORION] Ordre exécuté: ", action, " | Lot:", lot, " SL:", sl, " TP:", tp);
      else
         Print("[ORION] Erreur ordre: ", GetLastError());

      // Confirme l'exécution à Orion
      string confirm = "{\"action\":\"" + action + "\",\"executed\":" + (ok ? "true" : "false") + ",\"ticket\":" + (string)trade.ResultOrder() + "}";
      string r2 = "";
      HTTPSend("/api/trade-confirm", confirm, r2);
   }
   else if (action == "CLOSE_ALL") {
      CloseAllPositions();
   }
   else if (action == "CLOSE") {
      long ticket = (long)ExtractJSONDouble(response, "ticket");
      trade.PositionClose(ticket);
   }
   else if (action == "MODIFY") {
      long ticket = (long)ExtractJSONDouble(response, "ticket");
      double sl = ExtractJSONDouble(response, "sl");
      double tp = ExtractJSONDouble(response, "tp");
      trade.PositionModify(ticket, sl, tp);
   }
}

void CloseAllPositions() {
   for (int i = PositionsTotal() - 1; i >= 0; i--) {
      if (posInfo.SelectByIndex(i) && posInfo.Magic() == MagicNumber)
         trade.PositionClose(posInfo.Ticket());
   }
}

//+------------------------------------------------------------------+
//| Calcul de la taille de position                                  |
//+------------------------------------------------------------------+
double CalculateLotSize(double sl_price) {
   double balance     = AccountInfoDouble(ACCOUNT_BALANCE);
   double riskAmount  = balance * RiskPercent / 100.0;
   double tickValue   = SymbolInfoDouble(Symbol_, SYMBOL_TRADE_TICK_VALUE);
   double tickSize    = SymbolInfoDouble(Symbol_, SYMBOL_TRADE_TICK_SIZE);
   double currentAsk  = SymbolInfoDouble(Symbol_, SYMBOL_ASK);
   double slPips      = MathAbs(currentAsk - sl_price) / tickSize;
   if (slPips <= 0) return 0.01;
   double lot = NormalizeDouble(riskAmount / (slPips * tickValue), 2);
   double minLot = SymbolInfoDouble(Symbol_, SYMBOL_VOLUME_MIN);
   double maxLot = SymbolInfoDouble(Symbol_, SYMBOL_VOLUME_MAX);
   return MathMax(minLot, MathMin(maxLot, lot));
}

//+------------------------------------------------------------------+
//| HTTP helpers                                                      |
//+------------------------------------------------------------------+
int HTTPSend(string endpoint, string body, string &response) {
   string headers = "Content-Type: application/json\r\nX-Orion-Token: " + OrionToken + "\r\n";
   char   bodyArr[], resArr[];
   StringToCharArray(body, bodyArr, 0, StringLen(body));
   int code = WebRequest("POST", OrionURL + endpoint, headers, httpTimeout, bodyArr, resArr, headers);
   if (ArraySize(resArr) > 0) response = CharArrayToString(resArr);
   return code;
}

int HTTPGet(string endpoint, string &response) {
   string headers = "X-Orion-Token: " + OrionToken + "\r\n";
   char   bodyArr[], resArr[];
   int code = WebRequest("GET", OrionURL + endpoint, headers, httpTimeout, bodyArr, resArr, headers);
   if (ArraySize(resArr) > 0) response = CharArrayToString(resArr);
   return code;
}

//+------------------------------------------------------------------+
//| Parseurs JSON minimaux                                           |
//+------------------------------------------------------------------+
string ExtractJSONString(string json, string key) {
   string search = "\"" + key + "\":\"";
   int start = StringFind(json, search);
   if (start < 0) return "";
   start += StringLen(search);
   int end = StringFind(json, "\"", start);
   if (end < 0) return "";
   return StringSubstr(json, start, end - start);
}

double ExtractJSONDouble(string json, string key) {
   string search = "\"" + key + "\":";
   int start = StringFind(json, search);
   if (start < 0) return 0;
   start += StringLen(search);
   // Skip quote if string
   if (StringSubstr(json, start, 1) == "\"") start++;
   string num = "";
   for (int i = start; i < StringLen(json); i++) {
      string ch = StringSubstr(json, i, 1);
      if (ch == "," || ch == "}" || ch == "\"" || ch == "]") break;
      num += ch;
   }
   return StringToDouble(num);
}
