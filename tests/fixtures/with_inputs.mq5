//+------------------------------------------------------------------+
//| with_inputs.mq5 - for parser unit tests                          |
//+------------------------------------------------------------------+
#property version "1.0"
#include <Trade\Trade.mqh>
#include "../shared/helpers.mqh"

input int    MagicNumber = 1234;          // Magic number
input double LotSize     = 0.10;          // Lot size
input string CommentText = "hello";       // Trade comment
input bool   UseFilter   = true;          // Filter on/off
sinput int   HiddenParam = 0;
extern double LegacyLot  = 0.01;

// A commented-out include that must NOT be picked up:
// #include "commented.mqh"

int OnInit()  { return INIT_SUCCEEDED; }
void OnTick() {}
