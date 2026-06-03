function y = intmatvecmul(A,x)

[m,n]=size(A);

for i=1:m
    y(i,1)=0;
    y(i,2)=0;
    for j=1:n
        if A(i,j) >= 0
            y(i,:)=y(i,:)+A(i,j)*x(j,:);
        else
          
            y(i,:)=y(i,:)+A(i,j)*[x(j,2),x(j,1)];
        end
    end
end