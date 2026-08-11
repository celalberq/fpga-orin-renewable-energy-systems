`timescale 1ns / 1ps

module tracker_payload_rom (
    input wire [15:0] seq,
    input wire [7:0] index,
    output reg [7:0] char
);

    function [7:0] dec_digit5;
        input [15:0] value;
        input [2:0] digit_index;
        begin
            case (digit_index)
                3'd0: dec_digit5 = 8'd48 + ((value / 16'd10000) % 16'd10);
                3'd1: dec_digit5 = 8'd48 + ((value / 16'd1000) % 16'd10);
                3'd2: dec_digit5 = 8'd48 + ((value / 16'd100) % 16'd10);
                3'd3: dec_digit5 = 8'd48 + ((value / 16'd10) % 16'd10);
                3'd4: dec_digit5 = 8'd48 + (value % 16'd10);
                default: dec_digit5 = "?";
            endcase
        end
    endfunction

    always @* begin
        case (index)
            8'd0:   char = "t";
            8'd1:   char = "r";
            8'd2:   char = "k";
            8'd3:   char = ",";
            8'd4:   char = "s";
            8'd5:   char = "e";
            8'd6:   char = "q";
            8'd7:   char = "=";
            8'd8:   char = dec_digit5(seq, 3'd0);
            8'd9:   char = dec_digit5(seq, 3'd1);
            8'd10:  char = dec_digit5(seq, 3'd2);
            8'd11:  char = dec_digit5(seq, 3'd3);
            8'd12:  char = dec_digit5(seq, 3'd4);
            8'd13:  char = ",";
            8'd14:  char = "p";
            8'd15:  char = "a";
            8'd16:  char = "n";
            8'd17:  char = "=";
            8'd18:  char = "1";
            8'd19:  char = "2";
            8'd20:  char = "4";
            8'd21:  char = ".";
            8'd22:  char = "9";
            8'd23:  char = ",";
            8'd24:  char = "t";
            8'd25:  char = "i";
            8'd26:  char = "l";
            8'd27:  char = "t";
            8'd28:  char = "=";
            8'd29:  char = "1";
            8'd30:  char = "0";
            8'd31:  char = "2";
            8'd32:  char = ".";
            8'd33:  char = "6";
            8'd34:  char = ",";
            8'd35:  char = "s";
            8'd36:  char = "u";
            8'd37:  char = "n";
            8'd38:  char = "_";
            8'd39:  char = "p";
            8'd40:  char = "a";
            8'd41:  char = "n";
            8'd42:  char = "=";
            8'd43:  char = "1";
            8'd44:  char = "2";
            8'd45:  char = "7";
            8'd46:  char = ".";
            8'd47:  char = "0";
            8'd48:  char = ",";
            8'd49:  char = "s";
            8'd50:  char = "u";
            8'd51:  char = "n";
            8'd52:  char = "_";
            8'd53:  char = "t";
            8'd54:  char = "i";
            8'd55:  char = "l";
            8'd56:  char = "t";
            8'd57:  char = "=";
            8'd58:  char = "1";
            8'd59:  char = "0";
            8'd60:  char = "2";
            8'd61:  char = ".";
            8'd62:  char = "8";
            8'd63:  char = ",";
            8'd64:  char = "e";
            8'd65:  char = "r";
            8'd66:  char = "r";
            8'd67:  char = "=";
            8'd68:  char = "0";
            8'd69:  char = "0";
            8'd70:  char = "2";
            8'd71:  char = ".";
            8'd72:  char = "1";
            8'd73:  char = ",";
            8'd74:  char = "s";
            8'd75:  char = "t";
            8'd76:  char = "=";
            8'd77:  char = "l";
            8'd78:  char = "o";
            8'd79:  char = "c";
            8'd80:  char = "k";
            8'd81:  char = ",";
            8'd82:  char = "v";
            8'd83:  char = "_";
            8'd84:  char = "m";
            8'd85:  char = "v";
            8'd86:  char = "=";
            8'd87:  char = "0";
            8'd88:  char = "5";
            8'd89:  char = "5";
            8'd90:  char = "0";
            8'd91:  char = "6";
            8'd92:  char = ",";
            8'd93:  char = "i";
            8'd94:  char = "_";
            8'd95:  char = "m";
            8'd96:  char = "a";
            8'd97:  char = "=";
            8'd98:  char = "0";
            8'd99:  char = "0";
            8'd100: char = "4";
            8'd101: char = "2";
            8'd102: char = "1";
            8'd103: char = ",";
            8'd104: char = "p";
            8'd105: char = "_";
            8'd106: char = "m";
            8'd107: char = "w";
            8'd108: char = "=";
            8'd109: char = "0";
            8'd110: char = "2";
            8'd111: char = "3";
            8'd112: char = "1";
            8'd113: char = "8";
            8'd114: char = ",";
            8'd115: char = "s";
            8'd116: char = "r";
            8'd117: char = "c";
            8'd118: char = "=";
            8'd119: char = "i";
            8'd120: char = "n";
            8'd121: char = "a";
            8'd122: char = ",";
            8'd123: char = "a";
            8'd124: char = "c";
            8'd125: char = "t";
            8'd126: char = "=";
            8'd127: char = "s";
            8'd128: char = "w";
            default: char = "?";
        endcase
    end

endmodule
