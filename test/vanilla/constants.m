Fi = zeros(15, 12);
Fi(4:15,1:12) = eye(12, 12);

H_nom = zeros(3, 16);
H_nom(1:3, 1:3) = eye(3,3);