#define n 10

extern void abort(void); 
void reach_error(){}

void __VERIFIER_assert(int cond) {
  if (!(cond)) {
    ERROR: {reach_error();abort();}
  }
  return;
}
int __VERIFIER_nondet_int();

int main()
{

	int i,j,k;

	int A [n][n][n];
        int B [n][n][n];
        
        
        
	i=0;
	j=0;
	k=0;
	while(i < n){
		j=0;
		k=0;
		while(j < n){
			k=0;
			while(k < n){
                                        B[i][j][k]= __VERIFIER_nondet_int();
					k=k+1;
			}
			j=j+1;
		}
		i=i+1;
    }



	i=0;
	j=0;
	k=0;
	while(i < n){
		j=0;
		k=0;
		while(j < n){
			k=0;
			while(k < n){
					A[i][j][k]=B[n-i-1][n-j-1][n-k-1];
					k=k+1;
			}
			j=j+1;
		}
		i=i+1;
    }




	i=0;
	j=0;
	k=0;
	while(i < n){
		j=0;
		k=0;
		while(j < n){
			k=0;
			while(k < n){
					__VERIFIER_assert(A[i][j][k]==B[n-i-1][n-j-1][n-k-1]);
					k=k+1;
			}
			j=j+1;
		}
		i=i+1;
    }
return 0;
}
