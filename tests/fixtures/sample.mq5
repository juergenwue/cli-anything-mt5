//+------------------------------------------------------------------+
//| sample.mq5 - minimal EA for testing `climt5 compile`              |
//+------------------------------------------------------------------+
#property copyright "Test"
#property version   "0.1"

input int    MagicNumber = 1234;
input double LotSize     = 0.10;
input string Comment_    = "hello";

int OnInit()   { return INIT_SUCCEEDED; }
void OnDeinit(const int r) {}
void OnTick()  {}
