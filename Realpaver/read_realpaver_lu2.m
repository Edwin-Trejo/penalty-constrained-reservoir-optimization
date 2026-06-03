%
% filename-name of file
% n - number of variables
% eq - number of equations


function [lb,ub]=read_realpaver_lu2(filename,n,m)
   
    lb = [];
    ub = [];
    %%%%%% Read Realpaver file
    scanner = java.util.Scanner(java.io.FileInputStream(filename));
    %sets = (n*nfun);
    %lb=zeros(n,nfun);
    %Move sets+6 lines
    for i=1:(n+6)
       scanner.nextLine();
    end
    
    for i=1:n
        line = scanner.nextLine();
        position = strfind(line,' = ');
        if isempty(position) %there is an in
            position1 = strfind(line,' in ');
            position2 = strfind(line,' , ');
            if isempty(position2)
                disp('No Solution in the initial box');
                return;
            end
            value = line.substring(position1+4,position2);
            lb(i,1) = java.lang.Double.parseDouble(value);
            value = line.substring(position2+1,line.length-1);
            ub(i,1) = java.lang.Double.parseDouble(value);
        else
            value = line.substring(position+2,line.length);
            lb(i,1) = java.lang.Double.parseDouble(value);
            ub(i,1) = lb(i,1);
        end
    end
for k=1:m-1
    for i=1:4
       scanner.nextLine();
    end
    %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    % Second box
    
    for i=1:n
        line = scanner.nextLine();
        position = strfind(line,' = ');
        if isempty(position) %there is an in
            position1 = strfind(line,' in ');
            position2 = strfind(line,' , ');
            if isempty(position2)
                disp('No Solution in the initial box');
                return;
            end
            value = line.substring(position1+4,position2);
            lb(i,k+1) = java.lang.Double.parseDouble(value);
            value = line.substring(position2+1,line.length-1);
            ub(i,k+1) = java.lang.Double.parseDouble(value);
        else
            value = line.substring(position+2,line.length);
            lb(i,k+1) = java.lang.Double.parseDouble(value);
            ub(i,k+1) = lb(i,k+1);
        end
    end
end
 scanner.close();
end




