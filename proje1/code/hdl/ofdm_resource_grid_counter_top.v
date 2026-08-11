`timescale 1ns / 1ps

module ofdm_resource_grid_counter_top #(
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

    localparam integer MSG_LEN = 98;

    localparam [1:0] ST_WAIT = 2'd0;
    localparam [1:0] ST_SEND = 2'd1;

    reg [1:0] state = ST_WAIT;
    reg [31:0] interval_count = 32'd0;
    reg [7:0] message_index = 8'd0;
    reg [7:0] tx_data = 8'd0;
    reg tx_start = 1'b0;
    reg [15:0] frame_count = 16'd0;
    reg [15:0] seq_latched = 16'd0;
    reg heartbeat = 1'b0;

    wire uart_busy;
    wire uart_done;
    wire unused_uart_input = uart_tx_in;
    wire [7:0] unused_sw = sw;

    assign led[0] = 1'b1;
    assign led[1] = heartbeat;
    assign led[2] = uart_busy;
    assign led[3] = 1'b0;
    assign led[7:4] = 4'b0101;

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

    function [7:0] message_char;
        input [7:0] index;
        begin
            case (index)
                8'd0:  message_char = "p";
                8'd1:  message_char = "1";
                8'd2:  message_char = "o";
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
                8'd14: message_char = "f";
                8'd15: message_char = "f";
                8'd16: message_char = "t";
                8'd17: message_char = "=";
                8'd18: message_char = "0";
                8'd19: message_char = "6";
                8'd20: message_char = "4";
                8'd21: message_char = ",";
                8'd22: message_char = "c";
                8'd23: message_char = "p";
                8'd24: message_char = "=";
                8'd25: message_char = "0";
                8'd26: message_char = "1";
                8'd27: message_char = "6";
                8'd28: message_char = ",";
                8'd29: message_char = "d";
                8'd30: message_char = "a";
                8'd31: message_char = "t";
                8'd32: message_char = "a";
                8'd33: message_char = "=";
                8'd34: message_char = "0";
                8'd35: message_char = "4";
                8'd36: message_char = "8";
                8'd37: message_char = ",";
                8'd38: message_char = "p";
                8'd39: message_char = "i";
                8'd40: message_char = "l";
                8'd41: message_char = "o";
                8'd42: message_char = "t";
                8'd43: message_char = "=";
                8'd44: message_char = "0";
                8'd45: message_char = "0";
                8'd46: message_char = "4";
                8'd47: message_char = ",";
                8'd48: message_char = "o";
                8'd49: message_char = "f";
                8'd50: message_char = "d";
                8'd51: message_char = "m";
                8'd52: message_char = "=";
                8'd53: message_char = "0";
                8'd54: message_char = "0";
                8'd55: message_char = "8";
                8'd56: message_char = ",";
                8'd57: message_char = "f";
                8'd58: message_char = "r";
                8'd59: message_char = "a";
                8'd60: message_char = "m";
                8'd61: message_char = "e";
                8'd62: message_char = "_";
                8'd63: message_char = "b";
                8'd64: message_char = "=";
                8'd65: message_char = "0";
                8'd66: message_char = "0";
                8'd67: message_char = "0";
                8'd68: message_char = "8";
                8'd69: message_char = "7";
                8'd70: message_char = ",";
                8'd71: message_char = "q";
                8'd72: message_char = "p";
                8'd73: message_char = "s";
                8'd74: message_char = "k";
                8'd75: message_char = "=";
                8'd76: message_char = "0";
                8'd77: message_char = "0";
                8'd78: message_char = "3";
                8'd79: message_char = "4";
                8'd80: message_char = "8";
                8'd81: message_char = ",";
                8'd82: message_char = "p";
                8'd83: message_char = "a";
                8'd84: message_char = "d";
                8'd85: message_char = "=";
                8'd86: message_char = "0";
                8'd87: message_char = "0";
                8'd88: message_char = "0";
                8'd89: message_char = "7";
                8'd90: message_char = "2";
                8'd91: message_char = ",";
                8'd92: message_char = "o";
                8'd93: message_char = "k";
                8'd94: message_char = "=";
                8'd95: message_char = "1";
                8'd96: message_char = 8'h0D;
                8'd97: message_char = 8'h0A;
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
                    frame_count <= frame_count + 1'b1;
                    seq_latched <= frame_count + 1'b1;
                    heartbeat <= ~heartbeat;
                    state <= ST_SEND;
                end else begin
                    interval_count <= interval_count + 1;
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
