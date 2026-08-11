`timescale 1ns / 1ps

module qpsk_loopback_top #(
    parameter integer CLK_HZ = 100000000,
    parameter integer BAUD = 115200,
    parameter integer SEND_INTERVAL_CLKS = 100000000
) (
    input wire clk,
    input wire [7:0] sw,
    input wire uart_tx_in,
    output wire [7:0] led,
    output wire uart_rx_out
);

    localparam [8:0] SYMBOL_LAST_INDEX = 9'd347;
    localparam integer MSG_LEN = 73;

    localparam [1:0] ST_WAIT = 2'd0;
    localparam [1:0] ST_RUN  = 2'd1;
    localparam [1:0] ST_SEND = 2'd2;

    reg [1:0] state = ST_WAIT;
    reg [31:0] interval_count = 32'd0;
    reg [8:0] symbol_index = 9'd0;
    reg [7:0] message_index = 8'd0;
    reg [7:0] tx_data = 8'd0;
    reg tx_start = 1'b0;

    reg [15:0] frame_count = 16'd0;
    reg [15:0] seq_latched = 16'd0;
    reg [15:0] symbol_error_count = 16'd0;
    reg [15:0] bit_error_count = 16'd0;
    reg [15:0] symbol_error_latched = 16'd0;
    reg [15:0] bit_error_latched = 16'd0;
    reg [7:0] error_mask_latched = 8'd0;
    reg injected_latched = 1'b0;
    reg last_ok = 1'b1;
    reg heartbeat = 1'b0;

    wire uart_busy;
    wire uart_done;
    wire unused_uart_input = uart_tx_in;

    wire [1:0] tx_bit_pair = frame_bit_pair(symbol_index);
    wire tx_i_positive;
    wire tx_q_positive;
    wire [8:0] inject_symbol_index = {1'b0, error_mask_latched};
    wire inject_symbol = (error_mask_latched != 8'd0) && (symbol_index == inject_symbol_index);
    wire rx_i_positive = tx_i_positive ^ inject_symbol;
    wire rx_q_positive = tx_q_positive ^ inject_symbol;
    wire [1:0] rx_bit_pair;
    wire symbol_error_now = rx_bit_pair != tx_bit_pair;
    wire [1:0] bit_error_now = {1'b0, (rx_bit_pair[1] ^ tx_bit_pair[1])} +
                                {1'b0, (rx_bit_pair[0] ^ tx_bit_pair[0])};
    wire [15:0] symbol_error_next = symbol_error_count + (symbol_error_now ? 16'd1 : 16'd0);
    wire [15:0] bit_error_next = bit_error_count + {14'd0, bit_error_now};

    assign led[0] = last_ok;
    assign led[1] = injected_latched;
    assign led[2] = uart_busy;
    assign led[3] = heartbeat;
    assign led[7:4] = sw[7:4];

    qpsk_mapper mapper_inst (
        .bit_pair(tx_bit_pair),
        .i_positive(tx_i_positive),
        .q_positive(tx_q_positive)
    );

    qpsk_demapper demapper_inst (
        .i_positive(rx_i_positive),
        .q_positive(rx_q_positive),
        .bit_pair(rx_bit_pair)
    );

    uart_tx #(
        .CLK_HZ(CLK_HZ),
        .BAUD(BAUD)
    ) uart_tx_inst (
        .clk(clk),
        .reset(1'b0),
        .tx_start(tx_start),
        .tx_data(tx_data),
        .tx_line(uart_rx_out),
        .busy(uart_busy),
        .done(uart_done)
    );

    function [1:0] frame_bit_pair;
        input [8:0] index;
        reg [7:0] data_byte;
        begin
            data_byte = frame_byte(index[8:2]);

            case (index[1:0])
                2'd0: frame_bit_pair = data_byte[7:6];
                2'd1: frame_bit_pair = data_byte[5:4];
                2'd2: frame_bit_pair = data_byte[3:2];
                2'd3: frame_bit_pair = data_byte[1:0];
                default: frame_bit_pair = 2'b00;
            endcase
        end
    endfunction

    function [7:0] frame_byte;
        input [6:0] index;
        begin
            case (index)
                7'd0: frame_byte = 8'hA5;
                7'd1: frame_byte = 8'h5A;
                7'd2: frame_byte = 8'h53;
                7'd86: frame_byte = 8'h0C;
                default: frame_byte = payload_char(index - 7'd3);
            endcase
        end
    endfunction

    function [7:0] payload_char;
        input [6:0] index;
        begin
            case (index)
                7'd0:  payload_char = "p";
                7'd1:  payload_char = "3";
                7'd2:  payload_char = ",";
                7'd3:  payload_char = "s";
                7'd4:  payload_char = "e";
                7'd5:  payload_char = "q";
                7'd6:  payload_char = "=";
                7'd7:  payload_char = "0";
                7'd8:  payload_char = "0";
                7'd9:  payload_char = "0";
                7'd10: payload_char = "0";
                7'd11: payload_char = "1";
                7'd12: payload_char = ",";
                7'd13: payload_char = "d";
                7'd14: payload_char = "_";
                7'd15: payload_char = "p";
                7'd16: payload_char = "c";
                7'd17: payload_char = "t";
                7'd18: payload_char = "=";
                7'd19: payload_char = "0";
                7'd20: payload_char = "0";
                7'd21: payload_char = "0";
                7'd22: payload_char = "5";
                7'd23: payload_char = "0";
                7'd24: payload_char = ",";
                7'd25: payload_char = "v";
                7'd26: payload_char = "_";
                7'd27: payload_char = "m";
                7'd28: payload_char = "v";
                7'd29: payload_char = "=";
                7'd30: payload_char = "1";
                7'd31: payload_char = "4";
                7'd32: payload_char = "5";
                7'd33: payload_char = "6";
                7'd34: payload_char = "0";
                7'd35: payload_char = ",";
                7'd36: payload_char = "i";
                7'd37: payload_char = "_";
                7'd38: payload_char = "m";
                7'd39: payload_char = "a";
                7'd40: payload_char = "=";
                7'd41: payload_char = "0";
                7'd42: payload_char = "1";
                7'd43: payload_char = "2";
                7'd44: payload_char = "6";
                7'd45: payload_char = "8";
                7'd46: payload_char = ",";
                7'd47: payload_char = "p";
                7'd48: payload_char = "_";
                7'd49: payload_char = "m";
                7'd50: payload_char = "w";
                7'd51: payload_char = "=";
                7'd52: payload_char = "1";
                7'd53: payload_char = "8";
                7'd54: payload_char = "4";
                7'd55: payload_char = "6";
                7'd56: payload_char = "2";
                7'd57: payload_char = ",";
                7'd58: payload_char = "m";
                7'd59: payload_char = "p";
                7'd60: payload_char = "p";
                7'd61: payload_char = "t";
                7'd62: payload_char = "=";
                7'd63: payload_char = "u";
                7'd64: payload_char = "p";
                7'd65: payload_char = ",";
                7'd66: payload_char = "f";
                7'd67: payload_char = "=";
                7'd68: payload_char = "0";
                7'd69: payload_char = ",";
                7'd70: payload_char = "c";
                7'd71: payload_char = "h";
                7'd72: payload_char = "k";
                7'd73: payload_char = "=";
                7'd74: payload_char = "C";
                7'd75: payload_char = "C";
                7'd76: payload_char = ",";
                7'd77: payload_char = "r";
                7'd78: payload_char = "a";
                7'd79: payload_char = "w";
                7'd80: payload_char = "=";
                7'd81: payload_char = "8";
                7'd82: payload_char = "0";
                default: payload_char = "?";
            endcase
        end
    endfunction

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

    function [7:0] hex_char;
        input [3:0] nibble;
        begin
            case (nibble)
                4'h0: hex_char = "0";
                4'h1: hex_char = "1";
                4'h2: hex_char = "2";
                4'h3: hex_char = "3";
                4'h4: hex_char = "4";
                4'h5: hex_char = "5";
                4'h6: hex_char = "6";
                4'h7: hex_char = "7";
                4'h8: hex_char = "8";
                4'h9: hex_char = "9";
                4'ha: hex_char = "A";
                4'hb: hex_char = "B";
                4'hc: hex_char = "C";
                4'hd: hex_char = "D";
                4'he: hex_char = "E";
                4'hf: hex_char = "F";
                default: hex_char = "?";
            endcase
        end
    endfunction

    function [7:0] message_char;
        input [7:0] index;
        begin
            case (index)
                8'd0:  message_char = "p";
                8'd1:  message_char = "1";
                8'd2:  message_char = "q";
                8'd3:  message_char = ",";
                8'd4:  message_char = "s";
                8'd5:  message_char = "e";
                8'd6:  message_char = "q";
                8'd7:  message_char = "=";
                8'd8:  message_char = dec_digit5(seq_latched, 3'd0);
                8'd9:  message_char = dec_digit5(seq_latched, 3'd1);
                8'd10: message_char = dec_digit5(seq_latched, 3'd2);
                8'd11: message_char = dec_digit5(seq_latched, 3'd3);
                8'd12: message_char = dec_digit5(seq_latched, 3'd4);
                8'd13: message_char = ",";
                8'd14: message_char = "s";
                8'd15: message_char = "y";
                8'd16: message_char = "m";
                8'd17: message_char = "s";
                8'd18: message_char = "=";
                8'd19: message_char = "0";
                8'd20: message_char = "0";
                8'd21: message_char = "3";
                8'd22: message_char = "4";
                8'd23: message_char = "8";
                8'd24: message_char = ",";
                8'd25: message_char = "i";
                8'd26: message_char = "n";
                8'd27: message_char = "j";
                8'd28: message_char = "=";
                8'd29: message_char = injected_latched ? "1" : "0";
                8'd30: message_char = ",";
                8'd31: message_char = "s";
                8'd32: message_char = "y";
                8'd33: message_char = "m";
                8'd34: message_char = "_";
                8'd35: message_char = "e";
                8'd36: message_char = "r";
                8'd37: message_char = "r";
                8'd38: message_char = "=";
                8'd39: message_char = dec_digit5(symbol_error_latched, 3'd0);
                8'd40: message_char = dec_digit5(symbol_error_latched, 3'd1);
                8'd41: message_char = dec_digit5(symbol_error_latched, 3'd2);
                8'd42: message_char = dec_digit5(symbol_error_latched, 3'd3);
                8'd43: message_char = dec_digit5(symbol_error_latched, 3'd4);
                8'd44: message_char = ",";
                8'd45: message_char = "b";
                8'd46: message_char = "i";
                8'd47: message_char = "t";
                8'd48: message_char = "_";
                8'd49: message_char = "e";
                8'd50: message_char = "r";
                8'd51: message_char = "r";
                8'd52: message_char = "=";
                8'd53: message_char = dec_digit5(bit_error_latched, 3'd0);
                8'd54: message_char = dec_digit5(bit_error_latched, 3'd1);
                8'd55: message_char = dec_digit5(bit_error_latched, 3'd2);
                8'd56: message_char = dec_digit5(bit_error_latched, 3'd3);
                8'd57: message_char = dec_digit5(bit_error_latched, 3'd4);
                8'd58: message_char = ",";
                8'd59: message_char = "m";
                8'd60: message_char = "a";
                8'd61: message_char = "s";
                8'd62: message_char = "k";
                8'd63: message_char = "=";
                8'd64: message_char = hex_char(error_mask_latched[7:4]);
                8'd65: message_char = hex_char(error_mask_latched[3:0]);
                8'd66: message_char = ",";
                8'd67: message_char = "o";
                8'd68: message_char = "k";
                8'd69: message_char = "=";
                8'd70: message_char = last_ok ? "1" : "0";
                8'd71: message_char = 8'h0D;
                8'd72: message_char = 8'h0A;
                default: message_char = "?";
            endcase
        end
    endfunction

    always @(posedge clk) begin
        tx_start <= 1'b0;

        case (state)
            ST_WAIT: begin
                message_index <= 8'd0;

                if (interval_count >= SEND_INTERVAL_CLKS - 1) begin
                    interval_count <= 32'd0;
                    symbol_index <= 9'd0;
                    symbol_error_count <= 16'd0;
                    bit_error_count <= 16'd0;
                    error_mask_latched <= sw;
                    state <= ST_RUN;
                end else begin
                    interval_count <= interval_count + 1;
                end
            end

            ST_RUN: begin
                symbol_error_count <= symbol_error_next;
                bit_error_count <= bit_error_next;

                if (symbol_index == SYMBOL_LAST_INDEX) begin
                    frame_count <= frame_count + 1'b1;
                    seq_latched <= frame_count + 1'b1;
                    symbol_error_latched <= symbol_error_next;
                    bit_error_latched <= bit_error_next;
                    injected_latched <= error_mask_latched != 8'd0;
                    last_ok <= (symbol_error_next == 16'd0) && (bit_error_next == 16'd0);
                    heartbeat <= ~heartbeat;
                    message_index <= 8'd0;
                    state <= ST_SEND;
                end else begin
                    symbol_index <= symbol_index + 1'b1;
                end
            end

            ST_SEND: begin
                if (!uart_busy && !tx_start) begin
                    if (message_index < MSG_LEN) begin
                        tx_data <= message_char(message_index);
                        tx_start <= 1'b1;
                        message_index <= message_index + 1'b1;
                    end else begin
                        state <= ST_WAIT;
                    end
                end
            end

            default: begin
                state <= ST_WAIT;
            end
        endcase
    end

endmodule
