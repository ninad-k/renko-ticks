//+------------------------------------------------------------------+
//|                                                TickCsvReader.mqh |
//|  Fast reader for multi-GB tick CSVs (QuantDataManager exports).  |
//|  Reads the file in large binary chunks and parses bytes by hand; |
//|  FileReadString() is far too slow for ~650M rows.                |
//|                                                                  |
//|  Accepted row formats (header / blank lines are skipped):        |
//|     20171001 22:01:01.008,1279.99,1280.14,500                    |
//|     2017.10.01 22:01:01.008,1279.99,1280.14                      |
//+------------------------------------------------------------------+
#ifndef RENKO_TICK_CSV_READER_MQH
#define RENKO_TICK_CSV_READER_MQH

const double RENKO_POW10[] = {1.0, 1e1, 1e2, 1e3, 1e4, 1e5, 1e6, 1e7, 1e8, 1e9, 1e10, 1e11, 1e12};

class CTickCsvReader
  {
private:
   int               m_h;
   uchar             m_buf[];
   int               m_chunk;
   int               m_len;
   int               m_pos;
   bool              m_eof;
   ulong             m_size;
   ulong             m_read;
   int               m_cacheYmd;
   long              m_cacheDayMs;
   long              m_badLines;

   //--- days since 1970-01-01 (proleptic Gregorian)
   static long       DaysFromCivil(int y, const int m, const int d)
     {
      y -= (m <= 2) ? 1 : 0;
      long era = (y >= 0 ? y : y - 399) / 400;
      long yoe = y - era * 400;
      long doy = (153 * (m + (m > 2 ? -3 : 9)) + 2) / 5 + d - 1;
      long doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
      return era * 146097 + doe - 719468;
     }

   bool              Refill()
     {
      int tail = m_len - m_pos;
      if(tail >= m_chunk)      // a single line longer than the buffer: corrupt input
         return false;
      if(tail > 0 && m_pos > 0)
        {
         if(m_pos >= tail)
            ArrayCopy(m_buf, m_buf, 0, m_pos, tail);
         else
            for(int j = 0; j < tail; j++)   // overlapping move
               m_buf[j] = m_buf[m_pos + j];
        }
      m_pos = 0;
      m_len = tail;
      uint got = FileReadArray(m_h, m_buf, m_len, m_chunk - m_len);
      if(got == 0)
        {
         m_eof = true;
         return false;
        }
      m_len += (int)got;
      m_read += got;
      return true;
     }

   int               Digits2(const int i) const { return (m_buf[i] - '0') * 10 + (m_buf[i + 1] - '0'); }

   //--- parse an unsigned decimal number starting at i, stops at the first non-number byte
   double            ParseNum(int &i, const int e) const
     {
      long v = 0;
      int dec = -1;
      while(i < e)
        {
         uchar c = m_buf[i];
         if(c >= '0' && c <= '9')
           {
            v = v * 10 + (c - '0');
            if(dec >= 0)
               dec++;
           }
         else
            if(c == '.' && dec < 0)
               dec = 0;
            else
               break;
         i++;
        }
      if(dec <= 0)
         return (double)v;
      return (dec <= 12) ? (double)v / RENKO_POW10[dec] : (double)v / MathPow(10.0, dec);
     }

public:
                     CTickCsvReader() : m_h(INVALID_HANDLE), m_chunk(0), m_len(0), m_pos(0), m_eof(false),
                        m_size(0), m_read(0), m_cacheYmd(0), m_cacheDayMs(0), m_badLines(0) {}
                    ~CTickCsvReader() { Close(); }

   bool              Open(const string name, const bool common_folder = true, const int chunk_bytes = 64 * 1024 * 1024)
     {
      Close();
      int flags = FILE_READ | FILE_BIN | FILE_SHARE_READ | (common_folder ? FILE_COMMON : 0);
      m_h = FileOpen(name, flags);
      if(m_h == INVALID_HANDLE)
         return false;
      m_chunk = chunk_bytes;
      if(ArrayResize(m_buf, m_chunk) != m_chunk)
        {
         Close();
         return false;
        }
      m_size = FileSize(m_h);
      m_read = 0;
      m_len = 0;
      m_pos = 0;
      m_eof = false;
      m_badLines = 0;
      return true;
     }

   void              Close()
     {
      if(m_h != INVALID_HANDLE)
         FileClose(m_h);
      m_h = INVALID_HANDLE;
      ArrayFree(m_buf);
     }

   //--- Next tick. Returns false at end of file.
   bool              Next(long &time_msc, double &bid, double &ask)
     {
      while(true)
        {
         int p = m_pos;
         int e = p;
         while(e < m_len && m_buf[e] != '\n')
            e++;
         if(e >= m_len)
           {
            if(!m_eof)
              {
               if(Refill())
                  continue;
               if(!m_eof)
                  return false;
               p = m_pos;
               e = m_len;
              }
            if(p >= m_len)
               return false;  // nothing left
            // fall through: last line without a trailing newline
           }
         m_pos = e + 1;
         if(e - p < 23 || m_buf[p] < '0' || m_buf[p] > '9')
            continue;         // header, blank or junk line
         int i = p;
         int y = Digits2(i) * 100 + Digits2(i + 2);
         i += 4;
         if(m_buf[i] == '.')
            i++;
         int mo = Digits2(i);
         i += 2;
         if(m_buf[i] == '.')
            i++;
         int d = Digits2(i);
         i += 3;              // day + separator
         int hh = Digits2(i);
         int mi = Digits2(i + 3);
         int ss = Digits2(i + 6);
         i += 8;
         int ms = 0;
         if(m_buf[i] == '.')
           {
            i++;
            int scale = 100;
            while(i < e && m_buf[i] >= '0' && m_buf[i] <= '9')
              {
               ms += (m_buf[i] - '0') * scale;
               scale /= 10;
               i++;
              }
           }
         if(i >= e || m_buf[i] != ',')
           {
            m_badLines++;
            continue;
           }
         i++;
         bid = ParseNum(i, e);
         if(i >= e || m_buf[i] != ',')
           {
            m_badLines++;
            continue;
           }
         i++;
         ask = ParseNum(i, e);
         int ymd = y * 10000 + mo * 100 + d;
         if(ymd != m_cacheYmd)
           {
            m_cacheYmd = ymd;
            m_cacheDayMs = DaysFromCivil(y, mo, d) * 86400000;
           }
         time_msc = m_cacheDayMs + ((hh * 60 + mi) * 60 + ss) * 1000L + ms;
         return true;
        }
      return false;
     }

   double            Progress() const
     {
      if(m_size == 0)
         return 0;
      ulong consumed = m_read - (ulong)(m_len - m_pos);
      return (double)consumed / (double)m_size;
     }
   ulong             Size()     const { return m_size; }
   long              BadLines() const { return m_badLines; }
  };

#endif
