`timescale 1ns / 1ps

module solar_ldr_uart_top #(
    parameter integer CLK_HZ = 100000000,
    parameter integer BAUD = 115200,
    parameter integer SEND_INTERVAL_CLKS = 50000000,
    parameter integer ADC_SAMPLE_INTERVAL_CLKS = 250000
) (
    input wire clk,
    input wire [7:0] sw,
    input wire uart_tx_in,
    input wire adc_miso,
    output wire [7:0] led,
    output wire uart_rx_out,
    output wire adc_cs_n,
    output wire adc_sclk,
    output wire adc_mosi
);

    localparam integer MSG_LEN = 56;

    reg [31:0] adc_sample_count = 32'd0;
    reg adc_start = 1'b0;
    reg [2:0] adc_channel = 3'd0;
    reg [11:0] panel_raw = 12'd0;
    reg [11:0] ldr_tl_raw = 12'd0;
    reg [11:0] ldr_tr_raw = 12'd0;
    reg [11:0] ldr_bl_raw = 12'd0;
    reg [11:0] ldr_br_raw = 12'd0;

    wire adc_busy;
    wire adc_done;
    wire [11:0] adc_sample_data;

    mcp3208_reader #(
        .CLK_HZ(CLK_HZ),
        .SPI_HZ(1000000)
    ) adc_reader (
        .clk(clk),
        .start(adc_start),
        .channel(adc_channel),
        .spi_miso(adc_miso),
        .spi_cs_n(adc_cs_n),
        .spi_sclk(adc_sclk),
        .spi_mosi(adc_mosi),
        .busy(adc_busy),
        .done(adc_done),
        .sample_data(adc_sample_data)
    );

    wire [12:0] left_sum = {1'b0, ldr_tl_raw} + {1'b0, ldr_bl_raw};
    wire [12:0] right_sum = {1'b0, ldr_tr_raw} + {1'b0, ldr_br_raw};
    wire [12:0] top_sum = {1'b0, ldr_tl_raw} + {1'b0, ldr_tr_raw};
    wire [12:0] bottom_sum = {1'b0, ldr_bl_raw} + {1'b0, ldr_br_raw};
    wire [31:0] panel_scaled_mv = ({20'd0, panel_raw} * 32'd18300) / 32'd4095;

    reg [31:0] send_interval_count = 32'd0;
    reg [15:0] seq_counter = 16'd0;
    reg [5:0] msg_index = 6'd0;
    reg [7:0] tx_data = 8'd0;
    reg tx_start = 1'b0;
    reg sending = 1'b0;
    reg heartbeat = 1'b0;

    reg [15:0] seq_latched = 16'd0;
    reg [15:0] panel_mv_latched = 16'd0;
    reg [11:0] ldr_tl_latched = 12'd0;
    reg [11:0] ldr_tr_latched = 12'd0;
    reg [11:0] ldr_bl_latched = 12'd0;
    reg [11:0] ldr_br_latched = 12'd0;

    wire uart_busy;
    wire uart_done;

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

    function [7:0] dec_digit4;
        input [11:0] value;
        input [1:0] digit_index;
        begin
            case (digit_index)
                2'd0: dec_digit4 = 8'd48 + ((value / 12'd1000) % 12'd10);
                2'd1: dec_digit4 = 8'd48 + ((value / 12'd100) % 12'd10);
                2'd2: dec_digit4 = 8'd48 + ((value / 12'd10) % 12'd10);
                2'd3: dec_digit4 = 8'd48 + (value % 12'd10);
                default: dec_digit4 = "?";
            endcase
        end
    endfunction

    function [7:0] message_char;
        input [5:0] index;
        begin
            case (index)
                6'd0: message_char = "l";
                6'd1: message_char = "d";
                6'd2: message_char = "r";
                6'd3: message_char = ",";
                6'd4: message_char = "s";
                6'd5: message_char = "e";
                6'd6: message_char = "q";
                6'd7: message_char = "=";
                6'd8: message_char = dec_digit5(seq_latched, 3'd0);
                6'd9: message_char = dec_digit5(seq_latched, 3'd1);
                6'd10: message_char = dec_digit5(seq_latched, 3'd2);
                6'd11: message_char = dec_digit5(seq_latched, 3'd3);
                6'd12: message_char = dec_digit5(seq_latched, 3'd4);
                6'd13: message_char = ",";
                6'd14: message_char = "p";
                6'd15: message_char = "v";
                6'd16: message_char = "=";
                6'd17: message_char = dec_digit5(panel_mv_latched, 3'd0);
                6'd18: message_char = dec_digit5(panel_mv_latched, 3'd1);
                6'd19: message_char = dec_digit5(panel_mv_latched, 3'd2);
                6'd20: message_char = dec_digit5(panel_mv_latched, 3'd3);
                6'd21: message_char = dec_digit5(panel_mv_latched, 3'd4);
                6'd22: message_char = ",";
                6'd23: message_char = "t";
                6'd24: message_char = "l";
                6'd25: message_char = "=";
                6'd26: message_char = dec_digit4(ldr_tl_latched, 2'd0);
                6'd27: message_char = dec_digit4(ldr_tl_latched, 2'd1);
                6'd28: message_char = dec_digit4(ldr_tl_latched, 2'd2);
                6'd29: message_char = dec_digit4(ldr_tl_latched, 2'd3);
                6'd30: message_char = ",";
                6'd31: message_char = "t";
                6'd32: message_char = "r";
                6'd33: message_char = "=";
                6'd34: message_char = dec_digit4(ldr_tr_latched, 2'd0);
                6'd35: message_char = dec_digit4(ldr_tr_latched, 2'd1);
                6'd36: message_char = dec_digit4(ldr_tr_latched, 2'd2);
                6'd37: message_char = dec_digit4(ldr_tr_latched, 2'd3);
                6'd38: message_char = ",";
                6'd39: message_char = "b";
                6'd40: message_char = "l";
                6'd41: message_char = "=";
                6'd42: message_char = dec_digit4(ldr_bl_latched, 2'd0);
                6'd43: message_char = dec_digit4(ldr_bl_latched, 2'd1);
                6'd44: message_char = dec_digit4(ldr_bl_latched, 2'd2);
                6'd45: message_char = dec_digit4(ldr_bl_latched, 2'd3);
                6'd46: message_char = ",";
                6'd47: message_char = "b";
                6'd48: message_char = "r";
                6'd49: message_char = "=";
                6'd50: message_char = dec_digit4(ldr_br_latched, 2'd0);
                6'd51: message_char = dec_digit4(ldr_br_latched, 2'd1);
                6'd52: message_char = dec_digit4(ldr_br_latched, 2'd2);
                6'd53: message_char = dec_digit4(ldr_br_latched, 2'd3);
                6'd54: message_char = 8'h0D;
                6'd55: message_char = 8'h0A;
                default: message_char = 8'h20;
            endcase
        end
    endfunction

    always @(posedge clk) begin
        adc_start <= 1'b0;
        tx_start <= 1'b0;

        if (!adc_busy) begin
            if (adc_sample_count == ADC_SAMPLE_INTERVAL_CLKS - 1) begin
                adc_sample_count <= 32'd0;
                adc_start <= 1'b1;
            end else begin
                adc_sample_count <= adc_sample_count + 1'b1;
            end
        end

        if (adc_done) begin
            case (adc_channel)
                3'd0: panel_raw <= adc_sample_data;
                3'd2: ldr_tl_raw <= adc_sample_data;
                3'd3: ldr_tr_raw <= adc_sample_data;
                3'd4: ldr_bl_raw <= adc_sample_data;
                3'd5: ldr_br_raw <= adc_sample_data;
                default: panel_raw <= panel_raw;
            endcase

            case (adc_channel)
                3'd0: adc_channel <= 3'd2;
                3'd2: adc_channel <= 3'd3;
                3'd3: adc_channel <= 3'd4;
                3'd4: adc_channel <= 3'd5;
                default: adc_channel <= 3'd0;
            endcase
        end

        if (!sending) begin
            if (send_interval_count == SEND_INTERVAL_CLKS - 1) begin
                send_interval_count <= 32'd0;
                msg_index <= 6'd0;
                sending <= 1'b1;
                heartbeat <= ~heartbeat;
                seq_latched <= seq_counter;
                panel_mv_latched <= panel_scaled_mv[15:0];
                ldr_tl_latched <= ldr_tl_raw;
                ldr_tr_latched <= ldr_tr_raw;
                ldr_bl_latched <= ldr_bl_raw;
                ldr_br_latched <= ldr_br_raw;
                seq_counter <= seq_counter + 1'b1;
            end else begin
                send_interval_count <= send_interval_count + 1'b1;
            end
        end else if (!uart_busy && !tx_start) begin
            if (msg_index < MSG_LEN) begin
                tx_data <= message_char(msg_index);
                tx_start <= 1'b1;
                msg_index <= msg_index + 1'b1;
            end else begin
                sending <= 1'b0;
            end
        end
    end

    assign led[0] = ~adc_cs_n;
    assign led[1] = heartbeat;
    assign led[2] = uart_busy;
    assign led[3] = right_sum > left_sum;
    assign led[4] = left_sum > right_sum;
    assign led[5] = bottom_sum > top_sum;
    assign led[6] = top_sum > bottom_sum;
    assign led[7] = (ldr_tl_raw > 12'd4000) || (ldr_tr_raw > 12'd4000) ||
                    (ldr_bl_raw > 12'd4000) || (ldr_br_raw > 12'd4000);

    wire unused_uart_tx = uart_tx_in;
    wire unused_uart_done = uart_done;
    wire [7:0] unused_switches = sw;

endmodule
