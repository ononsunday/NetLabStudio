#include <stdio.h>
#include <string.h>
#ifdef _WIN32
#include <winsock2.h>
#else
#include <unistd.h>
#include <sys/socket.h>
#include <arpa/inet.h>
#define closesocket close
#define SOCKET int
#define INVALID_SOCKET -1
#endif
int main(void) {
#ifdef _WIN32
    WSADATA w; if (WSAStartup(MAKEWORD(2,2), &w)) return 1;
#endif
    SOCKET listener=socket(AF_INET, SOCK_STREAM, 0), client=socket(AF_INET, SOCK_STREAM, 0);
    struct sockaddr_in addr; memset(&addr,0,sizeof addr); addr.sin_family=AF_INET; addr.sin_addr.s_addr=htonl(INADDR_LOOPBACK);
    if (bind(listener,(struct sockaddr*)&addr,sizeof addr) || listen(listener,2)) return 2;
#ifdef _WIN32
    int len=sizeof addr;
#else
    socklen_t len=sizeof addr;
#endif
    getsockname(listener,(struct sockaddr*)&addr,&len);
    if (connect(client,(struct sockaddr*)&addr,sizeof addr)) return 3;
    SOCKET peer=accept(listener,NULL,NULL); char data[128]={0};
    if (peer==INVALID_SOCKET) return 4;
    const char *message="C Winsock TCP echo"; send(client,message,(int)strlen(message),0);
    int n=recv(peer,data,sizeof(data)-1,0); if(n<=0) return 5; send(peer,data,n,0);
    memset(data,0,sizeof data); n=recv(client,data,sizeof(data)-1,0); if(n<=0) return 6;
    printf("%s\n",data); closesocket(peer); closesocket(client); closesocket(listener);
#ifdef _WIN32
    WSACleanup();
#endif
    return 0;
}
