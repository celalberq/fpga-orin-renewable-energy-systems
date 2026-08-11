`timescale 1ns / 1ps

module tracker_frame_qpsk_ofdm_batch_top #(
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

    localparam [7:0] PAYLOAD_LEN = 8'd129;
    localparam [7:0] CRC_REGION_LAST_INDEX = 8'd129;
    localparam integer MSG_LEN = 132;

    localparam integer FRAME_BYTES = 133;
    localparam integer QPSK_SYMBOLS = 532;
    localparam [9:0] QPSK_LAST_INDEX = 10'd531;

    localparam integer OFDM_SYMBOLS = 12;
    localparam integer FFT_SIZE = 64;
    localparam integer CP_LEN = 16;
    localparam integer SYMBOL_SAMPLES = FFT_SIZE + CP_LEN;
    localparam integer PAD_QPSK_SYMBOLS = 44;

    localparam [2:0] ST_WAIT = 3'd0;
    localparam [2:0] ST_CRC  = 3'd1;
    localparam [2:0] ST_MAP  = 3'd2;
    localparam [2:0] ST_OFDM = 3'd3;
    localparam [2:0] ST_SEND = 3'd4;

    reg [2:0] state = ST_WAIT;
    reg [31:0] interval_count = 32'd0;
    reg [7:0] crc_index = 8'd0;
    reg [7:0] message_index = 8'd0;
    reg [7:0] tx_data = 8'd0;
    reg tx_start = 1'b0;

    reg [15:0] frame_count = 16'd0;
    reg [15:0] seq_latched = 16'd0;
    reg [7:0] tx_crc = 8'd0;
    reg [7:0] crc_latched = 8'd0;
    reg crc_ok_latched = 1'b0;
    reg map_ok_latched = 1'b0;
    reg ofdm_ok_latched = 1'b0;
    reg heartbeat = 1'b0;

    reg [9:0] symbol_index = 10'd0;
    reg [15:0] symbol_count = 16'd0;
    reg [15:0] s00_count = 16'd0;
    reg [15:0] s01_count = 16'd0;
    reg [15:0] s11_count = 16'd0;
    reg [15:0] s10_count = 16'd0;

    reg [3:0] ofdm_index = 4'd0;
    reg [6:0] sample_index = 7'd0;
    reg [15:0] tx_sample_count = 16'd0;
    reg [15:0] cp_sample_count = 16'd0;
    reg [15:0] pilot_count = 16'd0;
    reg [15:0] null_count = 16'd0;
    reg [15:0] payload_q_count = 16'd0;
    reg [15:0] pad_q_count = 16'd0;

    wire uart_busy;
    wire uart_done;
    wire unused_uart_input = uart_tx_in;
    wire [7:0] unused_sw = sw;

    wire [7:0] frame_byte_index = symbol_index[9:2];
    wire [1:0] frame_pair_index = symbol_index[1:0];
    wire [7:0] payload_rom_index =
        (state == ST_CRC) ? (crc_index - 8'd1) : (frame_byte_index - 8'd3);
    wire [7:0] payload_char;

    wire [7:0] crc_data = (crc_index == 8'd0) ? PAYLOAD_LEN : payload_char;
    wire [7:0] crc_next;
    wire [7:0] crc_residue_next;

    wire [7:0] frame_byte = frame_data_byte(frame_byte_index);
    wire [1:0] bit_pair = qpsk_pair_from_byte(frame_byte, frame_pair_index);
    wire qpsk_i_positive;
    wire qpsk_q_positive;

    wire s00_hit = qpsk_i_positive && qpsk_q_positive;
    wire s01_hit = !qpsk_i_positive && qpsk_q_positive;
    wire s11_hit = !qpsk_i_positive && !qpsk_q_positive;
    wire s10_hit = qpsk_i_positive && !qpsk_q_positive;

    wire [15:0] s00_next = s00_count + (s00_hit ? 16'd1 : 16'd0);
    wire [15:0] s01_next = s01_count + (s01_hit ? 16'd1 : 16'd0);
    wire [15:0] s11_next = s11_count + (s11_hit ? 16'd1 : 16'd0);
    wire [15:0] s10_next = s10_count + (s10_hit ? 16'd1 : 16'd0);
    wire [15:0] symbol_count_next = symbol_count + 16'd1;
    wire [15:0] symbol_sum_next = s00_next + s01_next + s11_next + s10_next;

    wire in_cp = sample_index < CP_LEN;
    wire [6:0] fft_bin_wide = sample_index - CP_LEN;
    wire [5:0] fft_bin = fft_bin_wide[5:0];
    wire at_last_sample = sample_index == (SYMBOL_SAMPLES - 1);
    wire at_last_ofdm_symbol = ofdm_index == (OFDM_SYMBOLS - 1);

    wire data_slot = !in_cp && !is_null_bin(fft_bin) && !is_pilot_bin(fft_bin);
    wire payload_slot = data_slot && (payload_q_count < QPSK_SYMBOLS);
    wire pad_slot = data_slot && (payload_q_count >= QPSK_SYMBOLS);

    wire [15:0] tx_sample_next = tx_sample_count + 16'd1;
    wire [15:0] cp_sample_next = cp_sample_count + (in_cp ? 16'd1 : 16'd0);
    wire [15:0] pilot_next = pilot_count + ((!in_cp && is_pilot_bin(fft_bin)) ? 16'd1 : 16'd0);
    wire [15:0] null_next = null_count + ((!in_cp && is_null_bin(fft_bin)) ? 16'd1 : 16'd0);
    wire [15:0] payload_q_next = payload_q_count + (payload_slot ? 16'd1 : 16'd0);
    wire [15:0] pad_q_next = pad_q_count + (pad_slot ? 16'd1 : 16'd0);

    wire ok_latched = crc_ok_latched && map_ok_latched && ofdm_ok_latched;

    assign led[0] = ok_latched;
    assign led[1] = heartbeat;
    assign led[2] = uart_busy;
    assign led[3] = state == ST_CRC || state == ST_MAP || state == ST_OFDM;
    assign led[7:4] = 4'b1010;

    tracker_payload_rom payload_rom_inst (
        .seq(seq_latched),
        .index(payload_rom_index),
        .char(payload_char)
    );

    crc8_byte crc_inst (
        .crc_in(tx_crc),
        .data_in(crc_data),
        .crc_out(crc_next)
    );

    crc8_byte crc_residue_inst (
        .crc_in(crc_next),
        .data_in(crc_next),
        .crc_out(crc_residue_next)
    );

    qpsk_mapper qpsk_mapper_inst (
        .bit_pair(bit_pair),
        .i_positive(qpsk_i_positive),
        .q_positive(qpsk_q_positive)
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

    function is_pilot_bin;
        input [5:0] bin;
        begin
            is_pilot_bin = (bin == 6'd11) || (bin == 6'd25) ||
                           (bin == 6'd39) || (bin == 6'd53);
        end
    endfunction

    function is_null_bin;
        input [5:0] bin;
        begin
            is_null_bin = (bin < 6'd6) || (bin == 6'd32) || (bin > 6'd58);
        end
    endfunction

    function [7:0] frame_data_byte;
        input [7:0] index;
        begin
            if (index == 8'd0) begin
                frame_data_byte = 8'hA5;
            end else if (index == 8'd1) begin
                frame_data_byte = 8'h5A;
            end else if (index == 8'd2) begin
                frame_data_byte = PAYLOAD_LEN;
            end else if (index == FRAME_BYTES - 1) begin
                frame_data_byte = crc_latched;
            end else begin
                frame_data_byte = payload_char;
            end
        end
    endfunction

    function [1:0] qpsk_pair_from_byte;
        input [7:0] byte_value;
        input [1:0] pair_index;
        begin
            case (pair_index)
                2'd0: qpsk_pair_from_byte = byte_value[7:6];
                2'd1: qpsk_pair_from_byte = byte_value[5:4];
                2'd2: qpsk_pair_from_byte = byte_value[3:2];
                2'd3: qpsk_pair_from_byte = byte_value[1:0];
                default: qpsk_pair_from_byte = 2'b00;
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
            if ((index >= 8'd10) && (index <= 8'd14)) begin
                message_char = dec_digit5(seq_latched, index - 8'd10);
            end else if ((index >= 8'd20) && (index <= 8'd24)) begin
                message_char = dec_digit5(symbol_count, index - 8'd20);
            end else if ((index >= 8'd30) && (index <= 8'd34)) begin
                message_char = dec_digit5(s00_count, index - 8'd30);
            end else if ((index >= 8'd40) && (index <= 8'd44)) begin
                message_char = dec_digit5(s01_count, index - 8'd40);
            end else if ((index >= 8'd50) && (index <= 8'd54)) begin
                message_char = dec_digit5(s11_count, index - 8'd50);
            end else if ((index >= 8'd60) && (index <= 8'd64)) begin
                message_char = dec_digit5(s10_count, index - 8'd60);
            end else if ((index >= 8'd71) && (index <= 8'd75)) begin
                message_char = dec_digit5(payload_q_count, index - 8'd71);
            end else if ((index >= 8'd81) && (index <= 8'd85)) begin
                message_char = dec_digit5(pad_q_count, index - 8'd81);
            end else if ((index >= 8'd93) && (index <= 8'd97)) begin
                message_char = dec_digit5(pilot_count, index - 8'd93);
            end else if ((index >= 8'd104) && (index <= 8'd108)) begin
                message_char = dec_digit5(null_count, index - 8'd104);
            end else if ((index >= 8'd113) && (index <= 8'd117)) begin
                message_char = dec_digit5(cp_sample_count, index - 8'd113);
            end else begin
                case (index)
                    8'd0:   message_char = "p";
                    8'd1:   message_char = "1";
                    8'd2:   message_char = "b";
                    8'd3:   message_char = "a";
                    8'd4:   message_char = "t";
                    8'd5:   message_char = ",";
                    8'd6:   message_char = "s";
                    8'd7:   message_char = "e";
                    8'd8:   message_char = "q";
                    8'd9:   message_char = "=";
                    8'd15:  message_char = ",";
                    8'd16:  message_char = "s";
                    8'd17:  message_char = "y";
                    8'd18:  message_char = "m";
                    8'd19:  message_char = "=";
                    8'd25:  message_char = ",";
                    8'd26:  message_char = "s";
                    8'd27:  message_char = "0";
                    8'd28:  message_char = "0";
                    8'd29:  message_char = "=";
                    8'd35:  message_char = ",";
                    8'd36:  message_char = "s";
                    8'd37:  message_char = "0";
                    8'd38:  message_char = "1";
                    8'd39:  message_char = "=";
                    8'd45:  message_char = ",";
                    8'd46:  message_char = "s";
                    8'd47:  message_char = "1";
                    8'd48:  message_char = "1";
                    8'd49:  message_char = "=";
                    8'd55:  message_char = ",";
                    8'd56:  message_char = "s";
                    8'd57:  message_char = "1";
                    8'd58:  message_char = "0";
                    8'd59:  message_char = "=";
                    8'd65:  message_char = ",";
                    8'd66:  message_char = "d";
                    8'd67:  message_char = "a";
                    8'd68:  message_char = "t";
                    8'd69:  message_char = "a";
                    8'd70:  message_char = "=";
                    8'd76:  message_char = ",";
                    8'd77:  message_char = "p";
                    8'd78:  message_char = "a";
                    8'd79:  message_char = "d";
                    8'd80:  message_char = "=";
                    8'd86:  message_char = ",";
                    8'd87:  message_char = "p";
                    8'd88:  message_char = "i";
                    8'd89:  message_char = "l";
                    8'd90:  message_char = "o";
                    8'd91:  message_char = "t";
                    8'd92:  message_char = "=";
                    8'd98:  message_char = ",";
                    8'd99:  message_char = "n";
                    8'd100: message_char = "u";
                    8'd101: message_char = "l";
                    8'd102: message_char = "l";
                    8'd103: message_char = "=";
                    8'd109: message_char = ",";
                    8'd110: message_char = "c";
                    8'd111: message_char = "p";
                    8'd112: message_char = "=";
                    8'd118: message_char = ",";
                    8'd119: message_char = "c";
                    8'd120: message_char = "r";
                    8'd121: message_char = "c";
                    8'd122: message_char = "=";
                    8'd123: message_char = hex_char(crc_latched[7:4]);
                    8'd124: message_char = hex_char(crc_latched[3:0]);
                    8'd125: message_char = ",";
                    8'd126: message_char = "o";
                    8'd127: message_char = "k";
                    8'd128: message_char = "=";
                    8'd129: message_char = ok_latched ? "1" : "0";
                    8'd130: message_char = 8'h0D;
                    8'd131: message_char = 8'h0A;
                    default: message_char = "?";
                endcase
            end
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
                    crc_index <= 8'd0;
                    tx_crc <= 8'd0;
                    crc_ok_latched <= 1'b0;
                    map_ok_latched <= 1'b0;
                    ofdm_ok_latched <= 1'b0;
                    symbol_index <= 10'd0;
                    symbol_count <= 16'd0;
                    s00_count <= 16'd0;
                    s01_count <= 16'd0;
                    s11_count <= 16'd0;
                    s10_count <= 16'd0;
                    ofdm_index <= 4'd0;
                    sample_index <= 7'd0;
                    tx_sample_count <= 16'd0;
                    cp_sample_count <= 16'd0;
                    pilot_count <= 16'd0;
                    null_count <= 16'd0;
                    payload_q_count <= 16'd0;
                    pad_q_count <= 16'd0;
                    state <= ST_CRC;
                end else begin
                    interval_count <= interval_count + 1;
                end
            end

            ST_CRC: begin
                tx_crc <= crc_next;

                if (crc_index == CRC_REGION_LAST_INDEX) begin
                    crc_latched <= crc_next;
                    crc_ok_latched <= crc_residue_next == 8'd0;
                    state <= ST_MAP;
                end else begin
                    crc_index <= crc_index + 1'b1;
                end
            end

            ST_MAP: begin
                symbol_count <= symbol_count_next;
                s00_count <= s00_next;
                s01_count <= s01_next;
                s11_count <= s11_next;
                s10_count <= s10_next;

                if (symbol_index == QPSK_LAST_INDEX) begin
                    map_ok_latched <= (symbol_count_next == QPSK_SYMBOLS) &&
                                      (symbol_sum_next == QPSK_SYMBOLS);
                    state <= ST_OFDM;
                end else begin
                    symbol_index <= symbol_index + 1'b1;
                end
            end

            ST_OFDM: begin
                tx_sample_count <= tx_sample_next;
                cp_sample_count <= cp_sample_next;
                pilot_count <= pilot_next;
                null_count <= null_next;
                payload_q_count <= payload_q_next;
                pad_q_count <= pad_q_next;

                if (at_last_sample) begin
                    sample_index <= 7'd0;

                    if (at_last_ofdm_symbol) begin
                        ofdm_ok_latched <= (tx_sample_next == 16'd960) &&
                                           (cp_sample_next == 16'd192) &&
                                           (pilot_next == 16'd48) &&
                                           (null_next == 16'd144) &&
                                           (payload_q_next == QPSK_SYMBOLS) &&
                                           (pad_q_next == PAD_QPSK_SYMBOLS);
                        heartbeat <= ~heartbeat;
                        state <= ST_SEND;
                    end else begin
                        ofdm_index <= ofdm_index + 1'b1;
                    end
                end else begin
                    sample_index <= sample_index + 1'b1;
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
