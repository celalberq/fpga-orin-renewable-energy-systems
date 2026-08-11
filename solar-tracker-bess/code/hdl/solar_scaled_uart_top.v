`timescale 1ns / 1ps

module solar_scaled_uart_top #(
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

    localparam integer MSG_LEN = 53;

    wire [7:0] duty_raw = sw;
    wire [15:0] duty_pct = ({8'd0, duty_raw} * 16'd100) / 16'd255;
    wire [15:0] voltage_mv = 16'd12000 + (duty_raw * 16'd20);
    wire [15:0] current_ma = 16'd500 + (duty_raw * 16'd6);
    wire [31:0] power_calc = voltage_mv * current_ma;
    wire [15:0] power_mw = power_calc / 32'd1000;
    wire fault = duty_raw >= 8'hF0;
    wire pwm_out;
    wire uart_busy;
    wire uart_done;

    reg [31:0] interval_count = 32'd0;
    reg [7:0] msg_index = 8'd0;
    reg [7:0] tx_data = 8'd0;
    reg tx_start = 1'b0;
    reg sending = 1'b1;
    reg heartbeat = 1'b0;

    assign led[0] = pwm_out;
    assign led[1] = heartbeat;
    assign led[2] = uart_busy;
    assign led[3] = fault;
    assign led[7:4] = duty_raw[7:4];

    pwm_generator #(
        .WIDTH(8)
    ) pwm_inst (
        .clk(clk),
        .duty(duty_raw),
        .pwm_out(pwm_out)
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
                8'd1:  message_char = "3";
                8'd2:  message_char = ",";
                8'd3:  message_char = "d";
                8'd4:  message_char = "_";
                8'd5:  message_char = "p";
                8'd6:  message_char = "c";
                8'd7:  message_char = "t";
                8'd8:  message_char = "=";
                8'd9:  message_char = dec_digit5(duty_pct, 3'd0);
                8'd10: message_char = dec_digit5(duty_pct, 3'd1);
                8'd11: message_char = dec_digit5(duty_pct, 3'd2);
                8'd12: message_char = dec_digit5(duty_pct, 3'd3);
                8'd13: message_char = dec_digit5(duty_pct, 3'd4);
                8'd14: message_char = ",";
                8'd15: message_char = "v";
                8'd16: message_char = "_";
                8'd17: message_char = "m";
                8'd18: message_char = "v";
                8'd19: message_char = "=";
                8'd20: message_char = dec_digit5(voltage_mv, 3'd0);
                8'd21: message_char = dec_digit5(voltage_mv, 3'd1);
                8'd22: message_char = dec_digit5(voltage_mv, 3'd2);
                8'd23: message_char = dec_digit5(voltage_mv, 3'd3);
                8'd24: message_char = dec_digit5(voltage_mv, 3'd4);
                8'd25: message_char = ",";
                8'd26: message_char = "i";
                8'd27: message_char = "_";
                8'd28: message_char = "m";
                8'd29: message_char = "a";
                8'd30: message_char = "=";
                8'd31: message_char = dec_digit5(current_ma, 3'd0);
                8'd32: message_char = dec_digit5(current_ma, 3'd1);
                8'd33: message_char = dec_digit5(current_ma, 3'd2);
                8'd34: message_char = dec_digit5(current_ma, 3'd3);
                8'd35: message_char = dec_digit5(current_ma, 3'd4);
                8'd36: message_char = ",";
                8'd37: message_char = "p";
                8'd38: message_char = "_";
                8'd39: message_char = "m";
                8'd40: message_char = "w";
                8'd41: message_char = "=";
                8'd42: message_char = dec_digit5(power_mw, 3'd0);
                8'd43: message_char = dec_digit5(power_mw, 3'd1);
                8'd44: message_char = dec_digit5(power_mw, 3'd2);
                8'd45: message_char = dec_digit5(power_mw, 3'd3);
                8'd46: message_char = dec_digit5(power_mw, 3'd4);
                8'd47: message_char = ",";
                8'd48: message_char = "f";
                8'd49: message_char = "=";
                8'd50: message_char = fault ? "1" : "0";
                8'd51: message_char = 8'h0d;
                8'd52: message_char = 8'h0a;
                default: message_char = 8'h20;
            endcase
        end
    endfunction

    always @(posedge clk) begin
        tx_start <= 1'b0;

        if (!sending) begin
            if (interval_count == SEND_INTERVAL_CLKS - 1) begin
                interval_count <= 32'd0;
                msg_index <= 8'd0;
                sending <= 1'b1;
                heartbeat <= ~heartbeat;
            end else begin
                interval_count <= interval_count + 1;
            end
        end else if (!uart_busy && !tx_start) begin
            if (msg_index < MSG_LEN) begin
                tx_data <= message_char(msg_index);
                tx_start <= 1'b1;
                msg_index <= msg_index + 1;
            end else begin
                sending <= 1'b0;
            end
        end
    end

    wire unused_uart_tx = uart_tx_in;
    wire unused_uart_done = uart_done;

endmodule
