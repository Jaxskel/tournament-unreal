// Original HTML5 definitions for the ping module's platform byte-order API.
// Browser builds exclude both its Windows and POSIX implementation files.
#include "CoreMinimal.h"
#if PLATFORM_HTML5
#include <arpa/inet.h>
uint16 HtoNS(uint16 value) { return htons(value); }
uint16 NtoHS(uint16 value) { return ntohs(value); }
uint32 HtoNL(uint32 value) { return htonl(value); }
uint32 NtoHL(uint32 value) { return ntohl(value); }
#endif
