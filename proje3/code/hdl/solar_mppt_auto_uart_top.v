`timescale 1ns / 1ps

module solar_mppt_auto_uart_top #(
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

    localparam integer MSG_LEN = 85;
    localparam [1:0] MPPT_HOLD = 2'd0;
    localparam [1:0] MPPT_UP   = 2'd1;
    localparam [1:0] MPPT_DN   = 2'd2;
    localparam [7:0] DUTY_STEP = 8'd4;

    reg [7:0] duty_cmd = 8'd32;
    reg step_dir_up = 1'b1;
    reg [15:0] prev_power_mw = 16'd0;
    reg [15:0] seq_counter = 16'd1;

    wire [7:0] mpp_target = 8'd64 + ({5'd0, sw[2:0]} * 8'd16);
    wire [7:0] irradiance = 8'd8 + ({5'd0, sw[5:3]} * 8'd2);
    wire [7:0] duty_raw = duty_cmd;
    wire [15:0] duty_pct_wire = ({8'd0, duty_raw} * 16'd100) / 16'd255;

    wire duty_above_mpp = duty_raw >= mpp_target;
    wire [7:0] distance_from_mpp = duty_above_mpp ? (duty_raw - mpp_target) : (mpp_target - duty_raw);
    wire [7:0] curve_shape = (distance_from_mpp >= 8'd128) ? 8'd0 : (8'd128 - distance_from_mpp);

    wire [15:0] voltage_mv_wire = 16'd11000 + ({8'd0, duty_raw} * 16'd20);
    wire [15:0] current_ma_wire = 16'd400 + (({8'd0, curve_shape} * {8'd0, irradiance}) / 16'd4);
    wire [31:0] power_calc_wire = voltage_mv_wire * current_ma_wire;
    wire [15:0] power_mw_wire = power_calc_wire / 32'd1000;

    wire fault_wire = sw[7] || (duty_raw >= 8'hF0);
    wire [1:0] mppt_code_wire =
        (power_mw_wire > prev_power_mw) ? MPPT_UP :
        (power_mw_wire < prev_power_mw) ? MPPT_DN :
        MPPT_HOLD;

    wire next_step_dir_up = (mppt_code_wire == MPPT_DN) ? ~step_dir_up : step_dir_up;
    wire [7:0] duty_step_up = (duty_cmd >= (8'hFF - DUTY_STEP)) ? 8'hFF : (duty_cmd + DUTY_STEP);
    wire [7:0] duty_step_dn = (duty_cmd <= DUTY_STEP) ? 8'd0 : (duty_cmd - DUTY_STEP);
    wire [7:0] duty_next = next_step_dir_up ? duty_step_up : duty_step_dn;

    wire [7:0] checksum_wire =
        seq_counter[7:0] ^
        seq_counter[15:8] ^
        duty_raw ^
        duty_pct_wire[7:0] ^
        voltage_mv_wire[7:0] ^
        voltage_mv_wire[15:8] ^
        current_ma_wire[7:0] ^
        current_ma_wire[15:8] ^
        power_mw_wire[7:0] ^
        power_mw_wire[15:8] ^
        {7'd0, fault_wire} ^
        {6'd0, mppt_code_wire};

    wire pwm_out;
    wire uart_busy;
    wire uart_done;

    reg [31:0] interval_count = 32'd0;
    reg [7:0] msg_index = 8'd0;
    reg [7:0] tx_data = 8'd0;
    reg tx_start = 1'b0;
    reg sending = 1'b1;
    reg heartbeat = 1'b0;

    reg [15:0] seq_latched = 16'd0;
    reg [7:0] duty_latched = 8'd0;
    reg [15:0] duty_pct_latched = 16'd0;
    reg [15:0] voltage_mv_latched = 16'd0;
    reg [15:0] current_ma_latched = 16'd0;
    reg [15:0] power_mw_latched = 16'd0;
    reg [1:0] mppt_code_latched = MPPT_HOLD;
    reg fault_latched = 1'b0;
    reg [7:0] checksum_latched = 8'd0;

    assign led[0] = pwm_out;
    assign led[1] = heartbeat;
    assign led[2] = uart_busy;
    assign led[3] = fault_latched;
    assign led[4] = step_dir_up;
    assign led[7:5] = sw[2:0];

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

    function [7:0] mppt_char;
        input [1:0] code;
        input second_char;
        begin
            case (code)
                MPPT_UP:   mppt_char = second_char ? "p" : "u";
                MPPT_DN:   mppt_char = second_char ? "n" : "d";
                default:   mppt_char = second_char ? "d" : "h";
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
                8'd13: message_char = "d";
                8'd14: message_char = "_";
                8'd15: message_char = "p";
                8'd16: message_char = "c";
                8'd17: message_char = "t";
                8'd18: message_char = "=";
                8'd19: message_char = dec_digit5(duty_pct_latched, 3'd0);
                8'd20: message_char = dec_digit5(duty_pct_latched, 3'd1);
                8'd21: message_char = dec_digit5(duty_pct_latched, 3'd2);
                8'd22: message_char = dec_digit5(duty_pct_latched, 3'd3);
                8'd23: message_char = dec_digit5(duty_pct_latched, 3'd4);
                8'd24: message_char = ",";
                8'd25: message_char = "v";
                8'd26: message_char = "_";
                8'd27: message_char = "m";
                8'd28: message_char = "v";
                8'd29: message_char = "=";
                8'd30: message_char = dec_digit5(voltage_mv_latched, 3'd0);
                8'd31: message_char = dec_digit5(voltage_mv_latched, 3'd1);
                8'd32: message_char = dec_digit5(voltage_mv_latched, 3'd2);
                8'd33: message_char = dec_digit5(voltage_mv_latched, 3'd3);
                8'd34: message_char = dec_digit5(voltage_mv_latched, 3'd4);
                8'd35: message_char = ",";
                8'd36: message_char = "i";
                8'd37: message_char = "_";
                8'd38: message_char = "m";
                8'd39: message_char = "a";
                8'd40: message_char = "=";
                8'd41: message_char = dec_digit5(current_ma_latched, 3'd0);
                8'd42: message_char = dec_digit5(current_ma_latched, 3'd1);
                8'd43: message_char = dec_digit5(current_ma_latched, 3'd2);
                8'd44: message_char = dec_digit5(current_ma_latched, 3'd3);
                8'd45: message_char = dec_digit5(current_ma_latched, 3'd4);
                8'd46: message_char = ",";
                8'd47: message_char = "p";
                8'd48: message_char = "_";
                8'd49: message_char = "m";
                8'd50: message_char = "w";
                8'd51: message_char = "=";
                8'd52: message_char = dec_digit5(power_mw_latched, 3'd0);
                8'd53: message_char = dec_digit5(power_mw_latched, 3'd1);
                8'd54: message_char = dec_digit5(power_mw_latched, 3'd2);
                8'd55: message_char = dec_digit5(power_mw_latched, 3'd3);
                8'd56: message_char = dec_digit5(power_mw_latched, 3'd4);
                8'd57: message_char = ",";
                8'd58: message_char = "m";
                8'd59: message_char = "p";
                8'd60: message_char = "p";
                8'd61: message_char = "t";
                8'd62: message_char = "=";
                8'd63: message_char = mppt_char(mppt_code_latched, 1'b0);
                8'd64: message_char = mppt_char(mppt_code_latched, 1'b1);
                8'd65: message_char = ",";
                8'd66: message_char = "f";
                8'd67: message_char = "=";
                8'd68: message_char = fault_latched ? "1" : "0";
                8'd69: message_char = ",";
                8'd70: message_char = "c";
                8'd71: message_char = "h";
                8'd72: message_char = "k";
                8'd73: message_char = "=";
                8'd74: message_char = hex_char(checksum_latched[7:4]);
                8'd75: message_char = hex_char(checksum_latched[3:0]);
                8'd76: message_char = ",";
                8'd77: message_char = "r";
                8'd78: message_char = "a";
                8'd79: message_char = "w";
                8'd80: message_char = "=";
                8'd81: message_char = hex_char(duty_latched[7:4]);
                8'd82: message_char = hex_char(duty_latched[3:0]);
                8'd83: message_char = 8'h0d;
                8'd84: message_char = 8'h0a;
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

                seq_latched <= seq_counter;
                duty_latched <= duty_raw;
                duty_pct_latched <= duty_pct_wire;
                voltage_mv_latched <= voltage_mv_wire;
                current_ma_latched <= current_ma_wire;
                power_mw_latched <= power_mw_wire;
                mppt_code_latched <= mppt_code_wire;
                fault_latched <= fault_wire;
                checksum_latched <= checksum_wire;

                prev_power_mw <= power_mw_wire;
                if (!fault_wire) begin
                    step_dir_up <= next_step_dir_up;
                    duty_cmd <= duty_next;
                end
                seq_counter <= seq_counter + 1'b1;
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
