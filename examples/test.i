# 1 "test.c"
# 1 "<built-in>" 1
# 1 "<built-in>" 3
# 331 "<built-in>" 3
# 1 "<command line>" 1
# 1 "<built-in>" 2
# 1 "test.c" 2

typedef char FOO;

char y[1];

int f(int x){
    return 2;
}

int main(void){

    int FOO = 0;
    int x = 0;
    int y = nondet();
    char y[3];
    int a = 1 | 2 & f(3);
    return 0;
}
