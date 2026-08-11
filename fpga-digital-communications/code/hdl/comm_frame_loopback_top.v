`timescale 1ns / 1ps

module comm_frame_loopback_top #(
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

    localparam [7:0] PAYLOAD_LEN = 8'd83;
    localparam [7:0] CRC_BYTES_LAST_INDEX = 8'd83;
    localparam [7:0] CORRUPT_PAYLOAD_INDEX = 8'd11;
    localparam integer MSG_LEN = 93;

    localparam [1:0] ST_WAIT = 2'd0;
    localparam [1:0] ST_CRC  = 2'd1;
    localparam [1:0] ST_SEND = 2'd2;

    reg [1:0] state = ST_WAIT;
    reg [31:0] interval_count = 32'd0;
    reg [7:0] crc_index = 8'd0;
    reg [7:0] message_index = 8'd0;
    reg [7:0] tx_data = 8'd0;
    reg tx_start = 1'b0;

    reg [15:0] frame_count = 16'd0;
    reg [15:0] crc_fail_count = 16'd0;
    reg [15:0] undetected_count = 16'd0;
    reg [15:0] seq_latched = 16'd0;
    reg [15:0] crc_fail_latched = 16'd0;
    reg [15:0] undetected_latched = 16'd0;
    reg [7:0] error_mask_latched = 8'd0;
    reg [7:0] tx_crc = 8'd0;
    reg [7:0] rx_crc = 8'd0;
    reg [7:0] tx_crc_latched = 8'd0;
    reg [7:0] rx_crc_latched = 8'd0;
    reg injected_latched = 1'b0;
    reg last_crc_ok = 1'b1;
    reg heartbeat = 1'b0;

    wire uart_busy;
    wire uart_done;
    wire unused_uart_input = uart_tx_in;

    wire crc_ok_now = tx_crc_next == rx_crc_next;
    wire injected_now = error_mask_latched != 8'd0;
    wire undetected_now = injected_now && crc_ok_now;
    wire crc_fail_now = !crc_ok_now;

    wire [7:0] clean_crc_data = crc_data_byte(crc_index, 1'b0);
    wire [7:0] rx_crc_data = crc_data_byte(crc_index, 1'b1);
    wire [7:0] tx_crc_next;
    wire [7:0] rx_crc_next;

    assign led[0] = last_crc_ok;
    assign led[1] = injected_latched;
    assign led[2] = uart_busy;
    assign led[3] = heartbeat;
    assign led[7:4] = sw[7:4];

    crc8_byte tx_crc_inst (
        .crc_in(tx_crc),
        .data_in(clean_crc_data),
        .crc_out(tx_crc_next)
    );

    crc8_byte rx_crc_inst (
        .crc_in(rx_crc),
        .data_in(rx_crc_data),
        .crc_out(rx_crc_next)
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

    function [7:0] crc_data_byte;
        input [7:0] index;
        input corrupt;
        reg [7:0] payload_index;
        reg [7:0] payload_data;
        begin
            if (index == 8'd0) begin
                crc_data_byte = PAYLOAD_LEN;
            end else begin
                payload_index = index - 8'd1;
                payload_data = payload_char(payload_index);

                if (corrupt && injected_now && payload_index == CORRUPT_PAYLOAD_INDEX) begin
                    crc_data_byte = payload_data ^ error_mask_latched;
                end else begin
                    crc_data_byte = payload_data;
                end
            end
        end
    endfunction

    function [7:0] payload_char;
        input [7:0] index;
        begin
            case (index)
                8'd0:  payload_char = "p";
                8'd1:  payload_char = "3";
                8'd2:  payload_char = ",";
                8'd3:  payload_char = "s";
                8'd4:  payload_char = "e";
                8'd5:  payload_char = "q";
                8'd6:  payload_char = "=";
                8'd7:  payload_char = "0";
                8'd8:  payload_char = "0";
                8'd9:  payload_char = "0";
                8'd10: payload_char = "0";
                8'd11: payload_char = "1";
                8'd12: payload_char = ",";
                8'd13: payload_char = "d";
                8'd14: payload_char = "_";
                8'd15: payload_char = "p";
                8'd16: payload_char = "c";
                8'd17: payload_char = "t";
                8'd18: payload_char = "=";
                8'd19: payload_char = "0";
                8'd20: payload_char = "0";
                8'd21: payload_char = "0";
                8'd22: payload_char = "5";
                8'd23: payload_char = "0";
                8'd24: payload_char = ",";
                8'd25: payload_char = "v";
                8'd26: payload_char = "_";
                8'd27: payload_char = "m";
                8'd28: payload_char = "v";
                8'd29: payload_char = "=";
                8'd30: payload_char = "1";
                8'd31: payload_char = "4";
                8'd32: payload_char = "5";
                8'd33: payload_char = "6";
                8'd34: payload_char = "0";
                8'd35: payload_char = ",";
                8'd36: payload_char = "i";
                8'd37: payload_char = "_";
                8'd38: payload_char = "m";
                8'd39: payload_char = "a";
                8'd40: payload_char = "=";
                8'd41: payload_char = "0";
                8'd42: payload_char = "1";
                8'd43: payload_char = "2";
                8'd44: payload_char = "6";
                8'd45: payload_char = "8";
                8'd46: payload_char = ",";
                8'd47: payload_char = "p";
                8'd48: payload_char = "_";
                8'd49: payload_char = "m";
                8'd50: payload_char = "w";
                8'd51: payload_char = "=";
                8'd52: payload_char = "1";
                8'd53: payload_char = "8";
                8'd54: payload_char = "4";
                8'd55: payload_char = "6";
                8'd56: payload_char = "2";
                8'd57: payload_char = ",";
                8'd58: payload_char = "m";
                8'd59: payload_char = "p";
                8'd60: payload_char = "p";
                8'd61: payload_char = "t";
                8'd62: payload_char = "=";
                8'd63: payload_char = "u";
                8'd64: payload_char = "p";
                8'd65: payload_char = ",";
                8'd66: payload_char = "f";
                8'd67: payload_char = "=";
                8'd68: payload_char = "0";
                8'd69: payload_char = ",";
                8'd70: payload_char = "c";
                8'd71: payload_char = "h";
                8'd72: payload_char = "k";
                8'd73: payload_char = "=";
                8'd74: payload_char = "C";
                8'd75: payload_char = "C";
                8'd76: payload_char = ",";
                8'd77: payload_char = "r";
                8'd78: payload_char = "a";
                8'd79: payload_char = "w";
                8'd80: payload_char = "=";
                8'd81: payload_char = "8";
                8'd82: payload_char = "0";
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
                8'd2:  message_char = ",";
                8'd3:  message_char = "s";
                8'd4:  message_char = "e";
                8'd5:  message_char = "q";
                8'd6:  message_char = "=";
                8'd7:  message_char = dec_digit5(seq_latched, 3'd0);
                8'd8:  message_char = dec_digit5(seq_latched, 3'd1);
                8'd9:  message_char = dec_digit5(seq_latched, 3'd2);
                8'd10: message_char = dec_digit5(seq_latched, 3'd3);
                8'd11: message_char = dec_digit5(seq_latched, 3'd4);
                8'd12: message_char = ",";
                8'd13: message_char = "p";
                8'd14: message_char = "a";
                8'd15: message_char = "y";
                8'd16: message_char = "l";
                8'd17: message_char = "o";
                8'd18: message_char = "a";
                8'd19: message_char = "d";
                8'd20: message_char = "=";
                8'd21: message_char = "p";
                8'd22: message_char = "3";
                8'd23: message_char = ",";
                8'd24: message_char = "l";
                8'd25: message_char = "e";
                8'd26: message_char = "n";
                8'd27: message_char = "=";
                8'd28: message_char = "0";
                8'd29: message_char = "0";
                8'd30: message_char = "0";
                8'd31: message_char = "8";
                8'd32: message_char = "3";
                8'd33: message_char = ",";
                8'd34: message_char = "i";
                8'd35: message_char = "n";
                8'd36: message_char = "j";
                8'd37: message_char = "=";
                8'd38: message_char = injected_latched ? "1" : "0";
                8'd39: message_char = ",";
                8'd40: message_char = "t";
                8'd41: message_char = "x";
                8'd42: message_char = "=";
                8'd43: message_char = hex_char(tx_crc_latched[7:4]);
                8'd44: message_char = hex_char(tx_crc_latched[3:0]);
                8'd45: message_char = ",";
                8'd46: message_char = "r";
                8'd47: message_char = "x";
                8'd48: message_char = "=";
                8'd49: message_char = hex_char(rx_crc_latched[7:4]);
                8'd50: message_char = hex_char(rx_crc_latched[3:0]);
                8'd51: message_char = ",";
                8'd52: message_char = "c";
                8'd53: message_char = "r";
                8'd54: message_char = "c";
                8'd55: message_char = "_";
                8'd56: message_char = "f";
                8'd57: message_char = "a";
                8'd58: message_char = "i";
                8'd59: message_char = "l";
                8'd60: message_char = "=";
                8'd61: message_char = dec_digit5(crc_fail_latched, 3'd0);
                8'd62: message_char = dec_digit5(crc_fail_latched, 3'd1);
                8'd63: message_char = dec_digit5(crc_fail_latched, 3'd2);
                8'd64: message_char = dec_digit5(crc_fail_latched, 3'd3);
                8'd65: message_char = dec_digit5(crc_fail_latched, 3'd4);
                8'd66: message_char = ",";
                8'd67: message_char = "u";
                8'd68: message_char = "n";
                8'd69: message_char = "d";
                8'd70: message_char = "e";
                8'd71: message_char = "t";
                8'd72: message_char = "=";
                8'd73: message_char = dec_digit5(undetected_latched, 3'd0);
                8'd74: message_char = dec_digit5(undetected_latched, 3'd1);
                8'd75: message_char = dec_digit5(undetected_latched, 3'd2);
                8'd76: message_char = dec_digit5(undetected_latched, 3'd3);
                8'd77: message_char = dec_digit5(undetected_latched, 3'd4);
                8'd78: message_char = ",";
                8'd79: message_char = "m";
                8'd80: message_char = "a";
                8'd81: message_char = "s";
                8'd82: message_char = "k";
                8'd83: message_char = "=";
                8'd84: message_char = hex_char(error_mask_latched[7:4]);
                8'd85: message_char = hex_char(error_mask_latched[3:0]);
                8'd86: message_char = ",";
                8'd87: message_char = "o";
                8'd88: message_char = "k";
                8'd89: message_char = "=";
                8'd90: message_char = last_crc_ok ? "1" : "0";
                8'd91: message_char = 8'h0D;
                8'd92: message_char = 8'h0A;
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
                    crc_index <= 8'd0;
                    tx_crc <= 8'd0;
                    rx_crc <= 8'd0;
                    error_mask_latched <= sw;
                    state <= ST_CRC;
                end else begin
                    interval_count <= interval_count + 1;
                end
            end

            ST_CRC: begin
                tx_crc <= tx_crc_next;
                rx_crc <= rx_crc_next;

                if (crc_index == CRC_BYTES_LAST_INDEX) begin
                    frame_count <= frame_count + 1'b1;
                    seq_latched <= frame_count + 1'b1;
                    tx_crc_latched <= tx_crc_next;
                    rx_crc_latched <= rx_crc_next;
                    last_crc_ok <= crc_ok_now;
                    injected_latched <= injected_now;
                    heartbeat <= ~heartbeat;

                    if (crc_fail_now) begin
                        crc_fail_count <= crc_fail_count + 1'b1;
                        crc_fail_latched <= crc_fail_count + 1'b1;
                    end else begin
                        crc_fail_latched <= crc_fail_count;
                    end

                    if (undetected_now) begin
                        undetected_count <= undetected_count + 1'b1;
                        undetected_latched <= undetected_count + 1'b1;
                    end else begin
                        undetected_latched <= undetected_count;
                    end

                    message_index <= 8'd0;
                    state <= ST_SEND;
                end else begin
                    crc_index <= crc_index + 1'b1;
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
